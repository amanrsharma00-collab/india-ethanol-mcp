from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from handlers import (
    handler_prices, handler_blending, handler_tenders,
    handler_depots, handler_notifications, handler_optimize
)
from analyze import handler as handler_analyze


ROUTES_GET = {
    "/api/v1/ethanol/prices":        handler_prices,
    "/api/v1/ethanol/blending":      handler_blending,
    "/api/v1/ethanol/tenders":       handler_tenders,
    "/api/v1/ethanol/depots":        handler_depots,
    "/api/v1/ethanol/notifications": handler_notifications,
}

ROUTES_POST = {
    "/api/v1/ethanol/optimize": handler_optimize,
    "/api/v1/ethanol/analyze":  handler_analyze,
}


class handler(BaseHTTPRequestHandler):

    def _build_event(self, body=None):
        parsed = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        return {
            "queryStringParameters": qs,
            "headers": dict(self.headers),
            "body": body,
            "path": parsed.path,
        }

    def _send(self, result):
        self.send_response(result.get("statusCode", 200))
        for k, v in result.get("headers", {}).items():
            self.send_header(k, v)
        self.end_headers()
        body = result.get("body", "")
        self.wfile.write(body.encode() if isinstance(body, str) else body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        event = self._build_event()

        # Debug endpoint — remove after confirming env vars work
        if path == "/api/debug":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "SUPABASE_URL": os.environ.get("SUPABASE_URL", "NOT SET"),
                "SERVICE_KEY_SET": bool(os.environ.get("SUPABASE_SERVICE_KEY")),
                "ANON_KEY_SET": bool(os.environ.get("SUPABASE_ANON_KEY")),
                "path": path,
            }).encode())
            return

        fn = ROUTES_GET.get(path)
        if fn:
            self._send(fn(event, {}))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Not found",
                "path": path,
                "available_routes": list(ROUTES_GET.keys()) + list(ROUTES_POST.keys())
            }).encode())

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else None
        event = self._build_event(body)

        fn = ROUTES_POST.get(path)
        if fn:
            self._send(fn(event, {}))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Not found", "path": path}).encode())

    def log_message(self, format, *args):
        pass  # Suppress default logging noise
