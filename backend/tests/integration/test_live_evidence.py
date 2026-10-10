from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit
import socket
import pytest
from app.modules.evidence import safe_http_client as safe_http
from app.modules.evidence import public_proxy_client as public_proxy
from app.modules.processing.workflow_service import StageFailure
from test_saved_evidence import screenshot


@pytest.fixture
def public_fixture(monkeypatch):
    visits = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            visits.append(self.path)
            if self.path == '/redirect-private':
                self.send_response(302); self.send_header('Location', 'http://127.0.0.1:' + str(self.server.server_port) + '/forbidden'); self.end_headers(); return
            if self.path == '/compressed':
                self.send_response(200); self.send_header('Content-Type', 'text/html'); self.send_header('Content-Encoding', 'gzip'); self.end_headers(); self.wfile.write(b'compressed'); return
            if self.path == '/attacks':
                private = 'http://127.0.0.1:' + str(self.server.server_port)
                content = ('<h1>Company</h1><img src="' + private + '/forbidden-image"><script>'
                    'fetch("'+private+'/forbidden-fetch").catch(()=>{});'
                    'try {new WebSocket("'+private.replace('http:','ws:')+'/forbidden-ws");} catch(e){}'
                    'fetch("http://rebind.example:'+str(self.server.server_port)+'/forbidden-rebind").catch(()=>{});'
                    '</script>').encode()
            elif self.path == '/large': content = b'a' * 2_000_001
            elif self.path == '/robots.txt': content = b'User-agent: *\nDisallow: /secret\n'
            elif self.path == '/about': content = b'<h1>About</h1><p>We develop accounting products.</p>'
            else: content = b'<title>Company</title><h1>Accounting software</h1><p>We sell bookkeeping tools.</p><a href="/about">About</a>'
            self.send_response(200); self.send_header('Content-Type', 'text/plain' if self.path == '/robots.txt' else 'text/html')
            self.send_header('Content-Length', str(len(content))); self.end_headers()
            try: self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError): pass
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    original = safe_http.destination
    def only_fixture(url):
        parsed = urlsplit(url)
        if parsed.hostname == 'fixture.example' and parsed.port == server.server_port:
            return url, parsed.hostname, parsed.port, '127.0.0.1'
        return original(url, resolver=lambda *args: ['127.0.0.1'])
    monkeypatch.setattr(safe_http, 'destination', only_fixture)
    monkeypatch.setattr(public_proxy, 'destination', only_fixture)
    try: yield 'http://fixture.example:' + str(server.server_port), visits
    finally: server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_redirect_to_private_is_blocked_without_a_connection(public_fixture):
    url, visits = public_fixture
    with pytest.raises(StageFailure, match='UNSAFE_DESTINATION'): safe_http.fetch(url + '/redirect-private')
    assert visits == ['/redirect-private']


@pytest.mark.parametrize('path,code', [('/large','PAGE_TOO_LARGE'),('/compressed','UNSUPPORTED_ENCODING')])
def test_transfer_limits_and_compression_cannot_bypass_bounds(public_fixture, path, code):
    with pytest.raises(StageFailure, match=code): safe_http.fetch(public_fixture[0] + path)


def test_live_collection_source_label_artifacts_support_pages_and_cleanup(client, job_lead, registered_worker, application, public_fixture, monkeypatch):
    from app.modules.evidence import safe_browser_client as safe_browser
    url, visits = public_fixture
    updated = client.patch('/api/v1/leads/' + job_lead['id'], json={'website': url}, headers={'If-Match': '"1"'}).json()
    monkeypatch.setattr(safe_browser, 'capture', lambda url, *args, **kwargs: (screenshot(),
        {'viewport': {'width':1366,'height':768}, 'browser':'test-only', 'final_url': url}, []))
    receipt = client.post('/api/v1/leads/' + job_lead['id'] + '/analysis-jobs',
        json={'mode':'live', 'include_supporting_pages':True}, headers={'Idempotency-Key':'live-fixture'})
    assert receipt.status_code == 202, receipt.text
    registered_worker.run_once()
    run = client.get('/api/v1/runs/' + receipt.json()['run_id']).json()
    assert run['score_result'] is not None, run
    assert run['visual_analysis']['result']['available']
    evidence = client.get('/api/v1/runs/' + receipt.json()['run_id'] + '/evidence').json()['items']
    assert len(evidence) == 2 and all(item['source_label'] == 'Live' and item['collected_at'] for item in evidence)
    text = next(item for item in evidence if item['kind'] == 'text')
    assert len(text['metadata']['pages']) == 2 and '/about' in visits
    assert 'artifact_key' not in str(evidence)
    image = next(item for item in evidence if item['kind'] == 'image')
    assert client.get(image['image_url']).content == screenshot()
    assert client.delete('/api/v1/leads/' + job_lead['id'] + '?confirm=true', headers={'If-Match': '"2"'}).status_code == 202


def test_robots_disallow_prevents_page_visit(public_fixture):
    from app.modules.evidence.live_evidence_service import RobotsPolicy
    url, visits = public_fixture; policy = RobotsPolicy(lambda: None)
    with pytest.raises(StageFailure, match='ROBOTS_DISALLOWED'):
        safe_http.fetch(url + '/secret', authorize=policy.authorize)
    assert visits == ['/robots.txt']


def test_http_socket_uses_resolved_ip_without_second_dns(monkeypatch):
    seen = []
    monkeypatch.setattr(safe_http, 'destination', lambda url: (url, 'company.example', 80, '8.8.8.8'))
    def connect(ip, port, timeout): seen.append((ip, port)); raise OSError('No real network in test')
    monkeypatch.setattr(safe_http, 'connect', connect)
    with pytest.raises(StageFailure, match='HTTP_FETCH_FAILED'): safe_http.fetch('http://company.example/')
    assert seen == [('8.8.8.8',80)]
