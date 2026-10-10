"""Bounded HTTP reads, exact-IP TLS with hostname verification, and safe redirects."""
from dataclasses import dataclass
import http.client
import ssl
import socket
import time
from urllib.parse import urlsplit, urljoin, quote
from app.modules.evidence.network_safety import destination, connect
from app.modules.processing.workflow_service import StageFailure

MAX_PAGE_BYTES = 2_000_000
USER_AGENT = 'LeadVision/0.12 (+manual company research; no authentication)'


@dataclass
class Page:
    url: str
    body: bytes
    headers: dict
    status: int


def fetch(url, checkpoint=lambda: None, *, html=True, limit=MAX_PAGE_BYTES, authorize=lambda url: None):
    deadline = time.monotonic() + 30
    for redirect in range(6):
        checkpoint()
        if time.monotonic() >= deadline: raise StageFailure('PAGE_TIMEOUT')
        normalized, host, port, ip = destination(url)
        authorize(normalized)
        sock = None
        try:
            sock = connect(ip, port, min(5, max(.1, deadline - time.monotonic())))
            if normalized.startswith('https:'):
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            connection = http.client.HTTPConnection(host, port, timeout=5)
            connection.sock = sock
            parsed = urlsplit(normalized)
            path = quote(parsed.path or '/', safe='/:%@!$&\'()*+,;=-._~')
            if parsed.query: path += '?' + quote(parsed.query, safe='=&%/:?@!$\'()*+,;~-._')
            connection.request('GET', path, headers={'Host': parsed.netloc, 'User-Agent': USER_AGENT,
                'Accept': 'text/html,application/xhtml+xml' if html else 'text/plain',
                'Accept-Encoding': 'identity', 'Connection': 'close'})
            response = connection.getresponse()
            headers = dict((key.lower(), value) for key, value in response.getheaders())
            if response.status in (301, 302, 303, 307, 308):
                if redirect == 5 or not headers.get('location'): raise StageFailure('REDIRECT_LIMIT')
                url = urljoin(normalized, headers['location']); continue
            if response.status in (401, 403, 429): raise StageFailure('ACCESS_DENIED')
            if response.status >= 400: raise StageFailure('HTTP_ERROR')
            # Ask for identity and reject non-compliant compressed responses rather than expand them.
            if headers.get('content-encoding', 'identity').lower() != 'identity': raise StageFailure('UNSUPPORTED_ENCODING')
            if html and headers.get('content-type', '').split(';')[0].strip().lower() not in ('text/html', 'application/xhtml+xml'):
                raise StageFailure('NON_HTML')
            if int(headers.get('content-length', '0')) > limit: raise StageFailure('PAGE_TOO_LARGE')
            chunks = []; size = 0
            while True:
                checkpoint()
                if response.isclosed() or response.length == 0: break
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise StageFailure('PAGE_TIMEOUT')
                sock.settimeout(min(5, remaining))
                chunk = response.read1(min(65536, limit + 1 - size))
                if not chunk: break
                chunks.append(chunk); size += len(chunk)
                if size > limit: raise StageFailure('PAGE_TOO_LARGE')
            return Page(normalized, b''.join(chunks), headers, response.status)
        except StageFailure: raise
        except TimeoutError: raise StageFailure('PAGE_TIMEOUT', retryable=True) from None
        except (OSError, ValueError, http.client.HTTPException): raise StageFailure('HTTP_FETCH_FAILED', retryable=True) from None
        finally:
            if sock: sock.close()
    raise StageFailure('REDIRECT_LIMIT')
