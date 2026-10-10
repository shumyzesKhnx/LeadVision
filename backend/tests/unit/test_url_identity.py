import pytest
from app.modules.foundation.urls import normalize_website


@pytest.mark.parametrize('url,domain,normalized', [
    (' HTTPS://WWW.Example.COM:443/a?utm_source=x#section ', 'example.com', 'https://www.example.com/a?utm_source=x'),
    ('http://example.com:80', 'example.com', 'http://example.com/'),
    ('https://example.com:8443/', 'example.com', 'https://example.com:8443/'),
    ('https://shop.example.com', 'shop.example.com', 'https://shop.example.com/'),
    ('https://bücher.de', 'xn--bcher-kva.de', 'https://xn--bcher-kva.de/'),
    ('https://example.com./', 'example.com', 'https://example.com/'),
    ('https://[2606:4700:4700:0:0:0:0:1111]/', '2606:4700:4700::1111', 'https://[2606:4700:4700::1111]/'),
])
def test_domain_identity_and_original_url(url, domain, normalized):
    value = normalize_website(url)
    assert value.original_url == url.strip()
    assert value.domain == domain
    assert value.normalized_url == normalized


@pytest.mark.parametrize('url', ['example.com', 'ftp://example.com', 'https://user:secret@example.com',
    'http://localhost', 'http://test.localhost', 'http://machine.local', 'http://127.0.0.1',
    'http://10.0.0.1', 'http://169.254.169.254', 'http://[::1]', 'http://[::ffff:127.0.0.1]',
    'http://224.0.0.1', 'http://127.1', 'http://2130706433', 'http://0x7f000001',
    'https://-bad.example.com', 'https://a..example.com', 'https://example.com:99999',
    'https://example.com:0', 'https://example.com\\x', 'https://example.com/a b', 'http://[invalid]/'])
def test_invalid_and_forbidden_websites(url):
    with pytest.raises(ValueError):
        normalize_website(url)
