"""Sample 'checkout' service with injectable faults.

Used to generate realistic failure logs for the Incident Management Copilot.
Stdlib only, so it runs anywhere without installing packages.

Endpoints:
  GET /checkout              simulated order request (may fail depending on fault)
  GET /health                liveness probe
  GET /admin/fault?mode=X    set the active fault: none | db_pool_exhaustion | disk_full | bad_deploy
"""

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

POOL_SIZE = 5
FAULT_MODES = {"none", "db_pool_exhaustion", "disk_full", "bad_deploy"}


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "service": "checkout",
            "msg": record.getMessage(),
        }
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload)


log = logging.getLogger("checkout")
_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
log.addHandler(_handler)
log.setLevel(logging.INFO)

pool = threading.BoundedSemaphore(POOL_SIZE)
_state_lock = threading.Lock()
_fault = {"mode": "none", "leaked": []}


def _leak_connections():
    """Simulate connections that are checked out and never returned."""
    held = []
    for _ in range(POOL_SIZE):
        pool.acquire()
        held.append(True)
    _fault["leaked"] = held


def _release_leaked():
    for _ in _fault["leaked"]:
        pool.release()
    _fault["leaked"] = []


def set_fault(mode):
    if mode not in FAULT_MODES:
        raise ValueError(f"unknown fault mode: {mode}")
    with _state_lock:
        _release_leaked()
        _fault["mode"] = mode
        if mode == "db_pool_exhaustion":
            _leak_connections()
        log.warning("fault mode changed", extra={"extra_fields": {"fault": mode}})


def handle_checkout():
    mode = _fault["mode"]

    if mode == "bad_deploy":
        log.error(
            "missing configuration key PAYMENT_GATEWAY_URL; checkout cannot start",
            extra={"extra_fields": {"status": 500, "route": "/checkout"}},
        )
        return 500, {"error": "internal configuration error"}

    if mode == "db_pool_exhaustion":
        if not pool.acquire(timeout=0.5):
            log.error(
                f"connection pool timeout after 0.5s; active={POOL_SIZE}/{POOL_SIZE}",
                extra={"extra_fields": {"status": 503, "route": "/checkout"}},
            )
            return 503, {"error": "service unavailable"}
        pool.release()

    if mode == "disk_full":
        log.error(
            "OSError: [Errno 28] No space left on device while writing order record",
            extra={"extra_fields": {"status": 500, "route": "/checkout"}},
        )
        return 500, {"error": "could not save order"}

    log.info("order accepted", extra={"extra_fields": {"status": 200, "route": "/checkout"}})
    return 200, {"status": "ok"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/health":
            return self._send(200, {"status": "up"})
        if url.path == "/checkout":
            status, body = handle_checkout()
            return self._send(status, body)
        if url.path == "/admin/fault":
            mode = parse_qs(url.query).get("mode", [""])[0]
            try:
                set_fault(mode)
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            return self._send(200, {"fault": mode})
        return self._send(404, {"error": "not found"})

    def log_message(self, format, *args):  # silence default access log
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    log.info("checkout service listening", extra={"extra_fields": {"port": 8080}})
    server.serve_forever()
