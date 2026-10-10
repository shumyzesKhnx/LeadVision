import socket
import pytest
from app.modules.evidence import safe_browser_client as safe_browser
from app.modules.evidence import public_proxy_client as public_proxy
from app.modules.processing.workflow_service import StageFailure
from test_live_evidence import public_fixture


def test_real_browser_capture_uses_proxy_and_records_viewport(public_fixture):
    url, visits = public_fixture
    original, info, warnings = safe_browser.capture(url)
    assert original.startswith(b'\x89PNG') and info['viewport'] == {'width':1366,'height':768}
    assert info['transferred_bytes'] > 0 and '/' in visits
    assert 'Chromium' in info['browser']


def test_proxy_blocks_http_and_connect_private_destinations_before_connect(monkeypatch):
    connected = []
    def unexpected(*args): connected.append(args); raise AssertionError('Forbidden connect')
    monkeypatch.setattr(public_proxy, 'connect', unexpected)
    for request in (b'GET http://127.0.0.1:8000/ HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n',
                    b'CONNECT 127.0.0.1:8000 HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n'):
        with public_proxy.PublicProxy() as proxy:
            port = int(proxy.url.rsplit(':',1)[1])
            with socket.create_connection(('127.0.0.1',port),timeout=3) as client:
                client.sendall(request); assert b'403 Forbidden' in client.recv(1000)
            assert 'UNSAFE_DESTINATION' in proxy.errors
    assert connected == []


def test_chrome_default_loopback_bypass_is_disabled(monkeypatch):
    from playwright.sync_api import sync_playwright, Error
    hits = []
    def unexpected(ip, *args):
        import ipaddress
        if not ipaddress.ip_address(ip).is_global: hits.append(ip)
        raise OSError('No outbound network in test')
    monkeypatch.setattr(public_proxy, 'connect', unexpected)
    with public_proxy.PublicProxy() as proxy, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=True, chromium_sandbox=True,
            proxy={'server':proxy.url, 'bypass':'<-loopback>'}, args=['--disable-quic'])
        try:
            with pytest.raises(Error, match='ERR_HTTP_RESPONSE_CODE_FAILURE'):
                browser.new_page().goto('http://127.0.0.1:8000/',wait_until='domcontentloaded',timeout=5000)
            assert 'UNSAFE_DESTINATION' in proxy.errors
        finally: browser.close()
    assert hits == []


def test_aggregate_proxy_budget_stops_transfers():
    with public_proxy.PublicProxy(max_bytes=3) as proxy:
        assert proxy.account(3)
        assert not proxy.account(1) and proxy.stop.is_set() and 'BROWSER_BYTES_LIMIT' in proxy.errors


def test_private_images_fetch_websocket_and_rebinding_never_reach_fixture(public_fixture):
    url, visits = public_fixture
    image, metadata, warnings = safe_browser.capture(url + '/attacks')
    assert image.startswith(b'\x89PNG')
    assert 'BROWSER_REQUEST_BLOCKED' in warnings and 'UNSAFE_DESTINATION' in warnings
    assert not any(path.startswith('/forbidden') for path in visits)


@pytest.mark.parametrize('url', ['file:///C:/Windows/win.ini','data:text/html,secret','javascript:alert(1)'])
def test_non_http_capture_is_rejected_before_browser(url):
    with pytest.raises(StageFailure, match='UNSAFE_DESTINATION'): safe_browser.capture(url)
