"""Fresh Chromium through an exact-IP proxy; no direct-network fallback."""
import time
import logging
from app.modules.foundation.urls import normalize_website
from app.modules.evidence.public_proxy_client import PublicProxy
from app.modules.processing.workflow_service import StageFailure

VIEWPORT = {'width': 1366, 'height': 768}


def capture(url, checkpoint=lambda: None, authorize=lambda url: None, *, channel='chrome'):
    from playwright.sync_api import sync_playwright, Error, TimeoutError as BrowserTimeout
    try: normalize_website(url)
    except ValueError: raise StageFailure('UNSAFE_DESTINATION') from None
    checkpoint(); authorize(url)
    warnings = set(); requests = [0]; deadline = time.monotonic() + 30
    with PublicProxy() as proxy, sync_playwright() as playwright:
        browser = None
        try:
            browser = playwright.chromium.launch(headless=True, timeout=10000, channel=channel, chromium_sandbox=True,
                proxy={'server': proxy.url, 'bypass': '<-loopback>'},
                args=['--disable-quic', '--disable-extensions', '--disable-background-networking',
                    '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
                    '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost',
                    '--disable-features=DnsOverHttps,AsyncDns'])
            context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1,
                service_workers='block', accept_downloads=False)
            context.set_default_timeout(3000)
            context.add_init_script("""for (const name of ['WebSocket','Worker','SharedWorker','RTCPeerConnection','webkitRTCPeerConnection']) {
                Object.defineProperty(globalThis, name, {value:class {constructor() {throw new DOMException('Disabled during capture','SecurityError');}}, writable:false, configurable:false});
            }""")
            context.route_web_socket('**/*', lambda websocket: websocket.close())
            def guard(route):
                checkpoint(); requests[0] += 1
                try:
                    normalize_website(route.request.url)
                    if route.request.method not in ('GET', 'HEAD'): raise ValueError('Method blocked')
                    if requests[0] > 100: raise ValueError('Request limit')
                    if route.request.is_navigation_request(): authorize(route.request.url)
                    if time.monotonic() >= deadline or proxy.stop.is_set(): raise ValueError('Capture limit')
                except (ValueError, StageFailure):
                    warnings.add('BROWSER_REQUEST_BLOCKED'); route.abort(); return
                route.continue_()
            context.route('**/*', guard)
            page = context.new_page()
            context.on('page', lambda popup: popup.close() if popup is not page else None)
            page.on('download', lambda download: download.cancel())
            navigation = page.goto(url, wait_until='domcontentloaded', timeout=max(1, int((deadline-time.monotonic())*1000)))
            if navigation is None or navigation.status >= 400: raise StageFailure('SCREENSHOT_BLOCKED')
            settled = time.monotonic() + .8
            while time.monotonic() < min(settled, deadline):
                checkpoint(); page.wait_for_timeout(100)
            normalize_website(page.url)
            visible = page.locator('body').inner_text(timeout=1000)[:1500].casefold()
            if any(phrase in visible for phrase in ('access denied', 'verify you are human', 'enable cookies')):
                raise StageFailure('SCREENSHOT_BLOCKED')
            if any(phrase in visible for phrase in ('accept all cookies', 'cookie consent')):
                warnings.add('CONSENT_MAY_OBSCURE_PAGE')
            checkpoint()
            if time.monotonic() >= deadline: raise StageFailure('PAGE_TIMEOUT')
            screenshot = page.screenshot(type='png', full_page=False, timeout=max(1, int((deadline-time.monotonic())*1000)))
            return screenshot, {'viewport': VIEWPORT, 'device_scale_factor': 1, 'browser': 'Chromium ' + browser.version,
                'final_url': page.url, 'requests': requests[0], 'transferred_bytes': proxy.bytes}, sorted(warnings | proxy.errors)
        except BrowserTimeout: raise StageFailure('PAGE_TIMEOUT', retryable=True) from None
        except Error as error:
            logging.getLogger('leadvision.browser').debug('Browser capture failed: %s', error)
            raise StageFailure('BROWSER_UNAVAILABLE') from error
        finally:
            if browser: browser.close()
