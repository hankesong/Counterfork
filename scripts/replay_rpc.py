"""Uncached, read-only retry gateway outside immutable producer source trees."""
import contextlib
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

READ_ONLY = {'eth_chainId', 'eth_getBlockByNumber', 'eth_getBlockByHash', 'eth_getLogs', 'eth_call',
             'eth_getTransactionReceipt', 'eth_getCode', 'eth_getStorageAt', 'eth_getBalance',
             'eth_getTransactionCount', 'eth_blockNumber', 'net_version', 'eth_getBlockReceipts'}
DELAYS = (2, 4, 8, 16, 32)  # Six attempts total, including the initial request.


def transient_error(exc):
    if isinstance(exc, HTTPError):
        return exc.code in (429, 502, 503, 504)
    if re.search(r'RPC error code -32\d+', str(exc)):
        return bool(re.search(r'RPC error code -32603: precondition failure\b', str(exc), re.I))
    return isinstance(exc, (URLError, TimeoutError, ConnectionError, OSError)) or bool(
        re.search(r'NETWORK_ERROR|timed out|timeout|SSL|connection reset|precondition failure', str(exc), re.I))


def transient_response(status, value):
    error = value.get('error') if isinstance(value, dict) else None
    if error:
        # Never retry explicit invalid params, unsupported method, or generic -32603.
        return error.get('code') == -32603 and error.get('message', '').strip().lower() == 'precondition failure'
    return status in (429, 502, 503, 504)


def read_retry(action, on_retry=lambda *_: None):
    for attempt in range(6):
        try:
            return action()
        except Exception as exc:
            if attempt == 5 or not transient_error(exc):
                raise
            on_retry(attempt + 1, DELAYS[attempt])
            time.sleep(DELAYS[attempt])


class Gateway:
    def __init__(self, url, state_path=None):
        self.url = url
        self.state_path = Path(state_path) if state_path else None
        self.lock = threading.Lock()
        self.stats = {'network_requests': 0, 'retries': 0, 'terminal_failures': 0}
        if self.state_path and self.state_path.exists():
            self.stats.update(json.loads(self.state_path.read_text(encoding='utf-8')))

    def count(self, key):
        with self.lock:
            self.stats[key] += 1
            if self.state_path:
                tmp = self.state_path.with_suffix('.tmp')
                tmp.write_text(json.dumps(self.stats), encoding='utf-8')
                tmp.replace(self.state_path)

    def exchange(self, payload):
        if not isinstance(payload, dict) or payload.get('method') not in READ_ONLY:
            raise ValueError('Method outside read-only allowlist; batches disabled')
        for attempt in range(6):
            try:
                self.count('network_requests')
                request = Request(self.url, data=json.dumps(payload).encode(), method='POST',
                                  headers={'Content-Type': 'application/json'})
                try:
                    response = urlopen(request, timeout=45)
                except HTTPError as exc:
                    response = exc
                with response:
                    status, body = response.code, response.read()
                try:
                    value = json.loads(body)
                except (ValueError, UnicodeDecodeError):
                    value = None
                retry = transient_response(status, value)
                if not retry:
                    if not isinstance(value, dict):
                        raise ValueError('Non-JSON RPC response (body discarded)')
                    return value
            except Exception as exc:
                if not transient_error(exc):
                    self.count('terminal_failures')
                    raise RuntimeError('Non-transient RPC transport failure; detail suppressed') from None
            if attempt == 5:
                self.count('terminal_failures')
                raise RuntimeError('Transient RPC failure exhausted six attempts; detail suppressed')
            self.count('retries')
            time.sleep(DELAYS[attempt])

    def preflight(self):
        def call(method, params):
            value = self.exchange({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})
            if value.get('error') or 'result' not in value:
                raise ValueError('RPC preflight failed: ' + method)
            return value['result']
        started = time.monotonic()
        if call('eth_chainId', []) != '0x1':
            raise ValueError('Reproduction node must be Ethereum chain 1')
        # cDAI decimals(), at a November 2020 block. A nonempty ABI word is required.
        value = call('eth_call', [{'to': '0x5d3a536e4d6dbd6114cc1ead35777bab948e3643',
                                  'data': '0x313ce567'}, hex(11333000)])
        if not isinstance(value, str) or not re.fullmatch(r'0x[0-9a-fA-F]{64}', value) or int(value, 16) != 8:
            raise ValueError('Historical eth_call preflight returned invalid cDAI decimals')
        return {'rpc_url_sha256': hashlib.sha256(self.url.encode()).hexdigest(), 'block': 11333000,
                'method': 'eth_call', 'result': value, 'elapsed_seconds': round(time.monotonic() - started, 3),
                **self.stats}

    @contextlib.contextmanager
    def serve(self):
        gateway = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                try:
                    payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    if not isinstance(payload, dict) or payload.get('method') not in READ_ONLY:
                        self.send_error(400)
                        return
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    # JSON whitespace keeps the old producer's 25-second socket alive
                    # during 32-second backoff, without touching its source or result.
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(gateway.exchange, payload)
                        while True:
                            try:
                                value = future.result(timeout=5)
                                break
                            except FutureTimeout:
                                self.wfile.write(b' ')
                                self.wfile.flush()
                            except Exception:
                                value = {'jsonrpc': '2.0', 'id': payload.get('id'), 'error': {
                                    'code': -32099, 'message': 'Gateway terminal transport failure'}}
                                break
                    # Preserve normal results. Provider error text may contain secrets.
                    if value.get('error'):
                        value['error']['message'] = 'Upstream RPC error (detail suppressed)'
                    self.wfile.write(json.dumps(value).encode())
                    self.wfile.flush()
                except (ConnectionError, OSError):
                    pass
                finally:
                    self.close_connection = True
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}'
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
