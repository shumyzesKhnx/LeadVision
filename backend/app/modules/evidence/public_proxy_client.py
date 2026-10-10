"""Per-capture loopback proxy. Every outbound socket uses a validated exact IP."""
import select
import socket
import socketserver
import threading
import time
from urllib.parse import urlsplit
from app.modules.evidence.network_safety import destination, connect
from app.modules.processing.workflow_service import StageFailure


class PublicProxy:
    def __init__(self, *, seconds=30, max_bytes=20_000_000):
        self.deadline = time.monotonic() + seconds
        self.max_bytes = max_bytes; self.bytes = 0
        self.errors = set(); self.connections = set()
        self.lock = threading.Lock(); self.stop = threading.Event()

    def account(self, size):
        with self.lock:
            self.bytes += size
            if self.bytes > self.max_bytes: self.errors.add('BROWSER_BYTES_LIMIT'); self.stop.set()
        return not self.stop.is_set() and time.monotonic() < self.deadline

    def __enter__(self):
        policy = self
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                client = self.request; remote = None
                with policy.lock: policy.connections.add(client)
                try:
                    client.settimeout(5); header = bytearray()
                    while not header.endswith(b'\r\n\r\n'):
                        if len(header) >= 16384: raise StageFailure('BROWSER_HEADER_LIMIT')
                        part = client.recv(1)
                        if not part: return
                        header.extend(part)
                        if policy.stop.is_set() or time.monotonic() >= policy.deadline: return
                    lines = bytes(header).decode('iso-8859-1').split('\r\n')
                    if any(line.lower().startswith('upgrade:') for line in lines[1:]):
                        raise StageFailure('BROWSER_REQUEST_BLOCKED')
                    method, target, version = lines[0].split(' ')
                    if method == 'CONNECT':
                        url = 'https://' + target + '/'
                    elif method in ('GET', 'HEAD'):
                        url = target
                    else: raise StageFailure('BROWSER_METHOD_BLOCKED')
                    normalized, host, port, ip = destination(url)
                    if not policy.account(len(header)): return
                    remote = connect(ip, port)
                    with policy.lock: policy.connections.add(remote)
                    if method == 'CONNECT':
                        client.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
                    else:
                        parsed = urlsplit(normalized)
                        path = parsed.path or '/'
                        if parsed.query: path += '?' + parsed.query
                        forwarded = [f'{method} {path} HTTP/1.1', 'Host: ' + parsed.netloc, 'Connection: close']
                        for line in lines[1:]:
                            if not line: continue
                            key, value = line.split(':', 1)
                            if key.lower() in {'host','connection','proxy-connection','proxy-authorization','upgrade','content-length','transfer-encoding'}: continue
                            forwarded.append(key + ':' + value)
                        remote.sendall(('\r\n'.join(forwarded) + '\r\n\r\n').encode('iso-8859-1'))
                    while not policy.stop.is_set() and time.monotonic() < policy.deadline:
                        readable, _, _ = select.select([client, remote], [], [], .2)
                        for source in readable:
                            chunk = source.recv(65536)
                            if not chunk: return
                            if not policy.account(len(chunk)): return
                            (remote if source is client else client).sendall(chunk)
                except StageFailure as error:
                    with policy.lock: policy.errors.add(error.code)
                    try: client.sendall(b'HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n')
                    except OSError: pass
                except (OSError, ValueError):
                    with policy.lock: policy.errors.add('BROWSER_CONNECTION_FAILED')
                finally:
                    for connection in (remote, client):
                        if connection:
                            with policy.lock: policy.connections.discard(connection)
                            connection.close()
        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            block_on_close = False
            slots = threading.BoundedSemaphore(32)
            def process_request(self, request, address):
                if not self.slots.acquire(blocking=False):
                    request.close(); return
                try: super().process_request(request, address)
                except BaseException:
                    self.slots.release(); raise
            def process_request_thread(self, request, address):
                try: super().process_request_thread(request, address)
                finally: self.slots.release()
        self.server = Server(('127.0.0.1', 0), Handler)
        self.url = 'http://127.0.0.1:' + str(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .1}, daemon=True)
        self.thread.start(); return self

    def __exit__(self, *args):
        self.stop.set()
        with self.lock: connections = list(self.connections)
        for connection in connections:
            try: connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=1)
