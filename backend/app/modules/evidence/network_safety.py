"""Resolve once, reject every non-public answer, then connect to that exact IP."""
import ipaddress
import socket
from queue import Queue, Empty
from threading import Thread, BoundedSemaphore
from urllib.parse import urlsplit
from app.modules.foundation.urls import normalize_website
from app.modules.processing.workflow_service import StageFailure

_dns_slots = BoundedSemaphore(8)


def resolve(host, port):
    result = Queue(maxsize=1)
    if not _dns_slots.acquire(blocking=False): raise StageFailure('DNS_FAILURE')
    def lookup():
        try: result.put(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except OSError: result.put(None)
        finally: _dns_slots.release()
    Thread(target=lookup, daemon=True).start()
    try: answers = result.get(timeout=5)
    except Empty: raise StageFailure('DNS_FAILURE') from None
    if not answers: raise StageFailure('DNS_FAILURE')
    return [answer[4][0] for answer in answers]


def destination(url, *, resolver=resolve):
    try:
        normalized = normalize_website(url).normalized_url
        parsed = urlsplit(normalized)
    except ValueError: raise StageFailure('UNSAFE_DESTINATION') from None
    host = parsed.hostname; port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    answers = resolver(host, port)
    if not answers: raise StageFailure('DNS_FAILURE')
    for answer in answers:
        try: address = ipaddress.ip_address(answer)
        except ValueError: raise StageFailure('DNS_FAILURE') from None
        if (not address.is_global or address.is_multicast or address.is_reserved
                or getattr(address, 'ipv4_mapped', None) is not None):
            raise StageFailure('UNSAFE_DESTINATION')
    return normalized, host, port, answers[0]


def connect(ip, port, timeout=5):
    # No hostname lookup happens here, including for IPv6.
    address = ipaddress.ip_address(ip)
    connection = socket.socket(socket.AF_INET6 if address.version == 6 else socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(timeout)
    try: connection.connect((str(address), port))
    except BaseException:
        connection.close(); raise
    return connection
