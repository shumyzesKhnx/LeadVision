"""Validate website syntax without fetching it; normalize company domain identity."""

from dataclasses import dataclass
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class WebsiteIdentity:
    original_url: str
    normalized_url: str
    domain: str


def normalize_website(value: str) -> WebsiteIdentity:
    original = value.strip()
    if not original or len(original) > 2048 or any(ord(char) <= 32 for char in original) or '\\' in original:
        raise ValueError('Enter a valid public HTTP/HTTPS website URL.')
    try:
        parsed = urlsplit(original)
        if parsed.scheme.lower() not in {'http', 'https'} or not parsed.netloc:
            raise ValueError('Website must start with http:// or https://.')
        if parsed.username is not None or parsed.password is not None:
            raise ValueError('Website credentials are not allowed.')
        host = parsed.hostname
        port = parsed.port
        if not host or (port is not None and not 1 <= port <= 65535):
            raise ValueError('Invalid hostname or port.')
        host = host.rstrip('.').encode('idna').decode('ascii').lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')) or '.' not in host:
                raise ValueError('Use a public website hostname.')
            if re.fullmatch(r'[0-9.]+', host) or host.startswith('0x'):
                raise ValueError('Ambiguous numeric hostnames are not allowed.')
            if len(host) > 253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                                      for label in host.split('.')):
                raise ValueError('Invalid website hostname.')
            normalized_host = host
        else:
            if not address.is_global or address.is_multicast:
                raise ValueError('Private, local or reserved IP addresses are not allowed.')
            normalized_host = f'[{address.compressed}]' if address.version == 6 else address.compressed
            host = address.compressed
        domain = host[4:] if host.startswith('www.') else host
        scheme = parsed.scheme.lower()
        authority = normalized_host
        if port is not None and (scheme, port) not in {('http', 80), ('https', 443)}:
            authority += f':{port}'
        normalized = urlunsplit((scheme, authority, parsed.path or '/', parsed.query, ''))
        return WebsiteIdentity(original, normalized, domain)
    except (UnicodeError, ValueError) as exc:
        raise ValueError('Enter a valid public HTTP/HTTPS URL without credentials.') from exc
