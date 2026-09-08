"""A closed local fixture: fixed requests to a server created within this process."""

from __future__ import annotations

import base64
import http.client
import json
import secrets
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fuzzrank.engines.base import observation
from fuzzrank.models import Observation
from fuzzrank.reporting.json_report import atomic_write

ROUTES = [
    "/admin",
    "/admin/export",
    "/api/users",
    "/swagger.json",
    "/home",
    "/welcome",
    "/assets/app.js",
    "/assets/logo.png",
    "/redirect",
    "/login",
    "/normal/missing",
    "/wild/one",
    "/wild/two",
    "/spa/one",
    "/spa/two",
] + [f"/missing-{i}" for i in range(20)]
BASELINE_PREFIXES = ["/", "/normal/", "/wild/", "/spa/"]


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):  # noqa: N802
        status, content_type, location = 200, "text/html; charset=utf-8", None
        body = "<html><title>Page unavailable</title><p>This route does not exist.</p></html>"
        if self.path == "/admin":
            status, body = (
                403,
                "<html><title>Administration</title><p>Staff access is required.</p></html>",
            )
        elif self.path == "/admin/export":
            status, body = 401, '{"error":"authentication required","operation":"export"}'
            content_type = "application/json"
        elif self.path == "/api/users":
            content_type, body = (
                "application/json",
                '{"users":[],"pagination":{"page":1,"total":0}}',
            )
        elif self.path == "/swagger.json":
            content_type = "application/json"
            body = '{"openapi":"3.0.3","info":{"title":"Local fixture","version":"1.0"},"paths":{}}'
        elif self.path in {"/home", "/welcome"}:
            body = "<html><title>Welcome</title><p>Welcome to this local demonstration.</p></html>"
        elif self.path == "/assets/app.js":
            content_type, body = (
                "application/javascript",
                "/* fixture static script */ console.log('demo');",
            )
        elif self.path == "/assets/logo.png":
            content_type, body = "image/png", "fixture-image-bytes"
        elif self.path == "/redirect":
            status, location, body = 302, "https://outside.example/", "External redirect fixture"
        elif self.path == "/login":
            status, location, body = 302, "/home", "Local redirect fixture"
        elif self.path.startswith("/normal/"):
            status, body = (
                404,
                "<html><title>Not found</title><p>There is no resource at this route.</p></html>",
            )
        elif self.path.startswith("/wild/"):
            body = (
                "<html><title>Wildcard</title><p>Every route in this section "
                "returns this page.</p></html>"
            )
        elif self.path.startswith("/spa/"):
            body = (
                '<html><title>SPA shell</title><div id="app">Application loading shell</div></html>'
            )
        # Volatile material tests normalization against multiple genuine HTTP responses.
        if content_type.startswith("text/html"):
            body += f'<!-- request_id="{secrets.token_hex(16)}" -->'
        encoded = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        if location:
            self.send_header("Location", location)
        self.end_headers()
        self.wfile.write(encoded)


@contextmanager
def local_application():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _request(server: ThreadingHTTPServer, path: str, number: int) -> Observation:
    host, port = server.server_address
    if host != "127.0.0.1":
        raise ValueError("The demonstration must use its own IPv4 loopback fixture")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read(1024 * 1024 + 1)
        truncated = len(body) > 1024 * 1024
        body = body[: 1024 * 1024]
        row = {
            "url": f"http://127.0.0.1:{port}{path}",
            "status_code": response.status,
            "headers": dict(response.getheaders()),
            "content_length": len(body),
            "word_count": len(body.split()),
            "line_count": len(body.splitlines()),
            "body_base64": base64.b64encode(body).decode(),
            "truncated": truncated,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return observation(row, engine="local-demo", source="local-demo", record=number)
    finally:
        connection.close()


def evidence_document(items: list[Observation]) -> bytes:
    rows = []
    for item in items:
        rows.append(
            {
                "engine": item.engine,
                "url": item.url,
                "method": item.method,
                "status_code": item.status_code,
                "content_length": item.content_length,
                "word_count": item.word_count,
                "line_count": item.line_count,
                "headers": item.headers,
                "content_type": item.content_type,
                "location": item.location,
                "body_base64": base64.b64encode(item.body).decode()
                if item.body is not None
                else None,
                "timestamp": item.timestamp,
                "truncated": item.truncated,
            }
        )
    return json.dumps({"format": "fuzzrank-evidence-v1", "observations": rows}, indent=2).encode()


def collect_demo(output: Path, max_requests: int = 64, announce=lambda phase, message: None):
    if not 3 <= max_requests <= 1000:
        raise ValueError("max_requests must be between 3 and 1000")
    discoveries, baselines, warnings = [], [], []
    partial = False
    with local_application() as server:
        target = f"http://127.0.0.1:{server.server_port}/"
        announce(1, f"Local fixture target and exact scope: {target}")
        announce(2, "Collecting 12 missing-path baseline responses")
        baseline_paths = [
            prefix + "fuzzrank-nonexistent-" + secrets.token_hex(16)
            for prefix in BASELINE_PREFIXES
            for _ in range(3)
        ]
        count = 0
        try:
            for is_baseline, paths in [(True, baseline_paths), (False, ROUTES)]:
                if not is_baseline:
                    announce(3, "Requesting the fixed local fixture paths (one request at a time)")
                for path in paths:
                    if count >= max_requests:
                        partial = True
                        break
                    count += 1
                    try:
                        item = _request(server, path, count)
                        (baselines if is_baseline else discoveries).append(item)
                    except (OSError, http.client.HTTPException) as exc:
                        warnings.append(f"Local request failed: {exc}")
                        partial = True
                    # Checkpoint both sets so interruption never loses completed responses.
                    atomic_write(output / "demo-evidence.json", evidence_document(discoveries))
                    atomic_write(output / "demo-baseline.json", evidence_document(baselines))
        except KeyboardInterrupt:
            warnings.append("Interrupted; completed local responses were preserved")
            partial = True
        if partial and count >= max_requests:
            warnings.append(
                f"Stopped at the {max_requests}-request limit, including baseline requests"
            )
    return target, discoveries, baselines, warnings, partial, count
