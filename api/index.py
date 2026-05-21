from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from handlers import (
    handler_prices, handler_blending, handler_tenders,
    handler_depots, handler_notifications, handler_optimize
)
from analyze import handler as handler_analyze


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = {}
        for k, v in parse_qs(parsed.query).items():
            qs[k] = v[0]

        event = {
            "queryStringParameters": qs,
            "headers": dict(self.headers),
            "body": None,
        }

        route_map = {
            "/api/v1/ethanol/prices":        handler_prices,
            "/api/v1/ethanol/blending":      handler_blending,
            "/api/v1/ethanol/tenders":       handler_tenders,
            "/api/v1/ethanol/depots":        handler_depots,
            "/api/v1/ethanol/notifications": handler_notifications,
        }

        fn = route_map.get(path)
        if fn:
            result = fn(event, {})
        else:
            result = {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

        self.send_response(result.get("statusCode", 200))
        for k, v in result.get("headers", {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(result["body"].encode())

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = {}
        for k, v in parse_qs(parsed.query).items():
            qs[k] = v[0]

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else None

        event = {
            "queryStringParameters": qs,
            "headers": dict(self.headers),
            "body": body,
        }

        route_map = {
            "/api/v1/ethanol/optimize": handler_optimize,
            "/api/v1/ethanol/analyze":  handler_analyze,
        }

        fn = route_map.get(path)
        if fn:
            result = fn(event, {})
        else:
            result = {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

        self.send_response(result.get("statusCode", 200))
        for k, v in result.get("headers", {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(result["body"].encode())
