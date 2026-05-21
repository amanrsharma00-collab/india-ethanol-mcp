from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from handlers import handler_depots

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        result = handler_depots({"queryStringParameters": qs, "headers": dict(self.headers), "body": None}, {})
        self.send_response(result["statusCode"])
        for k, v in result["headers"].items(): self.send_header(k, v)
        self.end_headers()
        self.wfile.write(result["body"].encode())
    def log_message(self, *args): pass
