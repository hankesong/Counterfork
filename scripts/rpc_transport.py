"""Shared read-only transport, credential redaction and cross-process 5 RPS cap."""
import contextlib
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
READ_ONLY = {"eth_chainId", "eth_getBlockByNumber", "eth_getBlockByHash",
             "eth_getLogs", "eth_call", "eth_getTransactionReceipt", "eth_getCode",
             "eth_getStorageAt", "eth_getBalance", "eth_getTransactionCount",
             "eth_blockNumber", "net_version"}
STATS = {"network_requests": 0, "cache_hits": 0}
_thread_lock = threading.Lock()


def config():
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def redact(value):
    text = str(value)
    for secret in sorted(set(config().values()), key=len, reverse=True):
        if secret:
            text = text.replace(secret, "[redacted credential]")
    return re.sub(r"https?://[^\s\"<>]+", "[redacted URL]", text)


def rate_limit():
    """Serialize request starts across all project processes, at most 5 per second."""
    path = ROOT / "data/private/rpc_rate.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    with _thread_lock, path.open("r+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0" * 32)
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.025)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            handle.seek(0)
            last = float(handle.read(32).decode().strip() or 0)
            time.sleep(max(0, last + 0.22 - time.time()))
            handle.seek(0)
            handle.write(f"{time.time():032.6f}".encode())
            handle.flush()
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def exchange(url, payload):
    if not isinstance(payload, dict) or payload.get("method") not in READ_ONLY:
        raise ValueError("Method outside the read-only allowlist; batches are disabled")
    request = Request(url, data=json.dumps(payload).encode(), method="POST",
                      headers={"Content-Type": "application/json", "Accept": "application/json",
                               "User-Agent": "CounterfactualInvestigator-Phase0/0.1"})
    rate_limit()
    STATS["network_requests"] += 1
    try:
        try:
            response = urlopen(request, timeout=25)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read()
            metadata = {"http_status": response.code,
                        "content_type": redact(response.headers.get("Content-Type", ""))}
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            title = re.search(r"<title[^>]*>(.*?)</title>", body.decode(errors="replace"), re.S | re.I)
            metadata["html_title"] = redact(title.group(1).strip()[:160]) if title else None
            data = None
        # Non-JSON bodies are never returned or saved.
        return metadata, data
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(redact(f"NETWORK_ERROR: {exc}")) from None


@contextlib.contextmanager
def rpc_proxy(upstream, observations=None):
    """Route cast/forge requests through the same limiter; discard HTML bodies."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            try:
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                metadata, data = exchange(upstream, payload)
                if observations is not None:
                    observations.append({"request": payload, **metadata})
                if data is None:
                    data = {"jsonrpc": "2.0", "id": payload.get("id"),
                            "error": {"code": -32000, "message": "NON_JSON_RESPONSE; see HTTP metadata"}}
                encoded = redact(json.dumps(data)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except Exception as exc:
                encoded = json.dumps({"jsonrpc": "2.0", "id": None, "error": {
                    "code": -32000, "message": redact(exc)}}).encode()
                self.send_response(502)
                self.end_headers()
                self.wfile.write(encoded)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield urlunsplit(("http", f"127.0.0.1:{server.server_port}", "", "", ""))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
