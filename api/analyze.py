from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from handlers import (
    EBP_PRICES, BLENDING_DATA, OMC_TENDERS,
    OMC_DEPOTS, CCEA_NOTIFICATIONS, LATEST_SEASON,
    validate_key, ok, err
)

LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "")
LLM_API_KEY  = os.environ.get("LLM_API_KEY", "")
LLM_MODEL    = os.environ.get("LLM_MODEL", "")


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        qs = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else None
        event = {"queryStringParameters": qs, "headers": dict(self.headers), "body": body}

        allowed, reason, meta = validate_key(event, "/v1/ethanol/analyze")
        if not allowed:
            result = err(401, reason)
        elif meta and meta.get("tier") == "free":
            result = err(403, "AI analysis requires Starter tier. Upgrade at gridintelin.com/pricing")
        elif not LLM_ENDPOINT:
            result = err(503, "LLM endpoint not configured.")
        else:
            try:
                body_data = json.loads(body or "{}")
            except:
                result = err(400, "Invalid JSON body.")
            else:
                result = self._analyze(body_data, meta)

        self.send_response(result["statusCode"])
        for k, v in result["headers"].items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(result["body"].encode())

    def _analyze(self, body, meta):
        import urllib.request, urllib.error
        query = body.get("query")
        if not query:
            return err(400, "Required: 'query' string")

        ctx  = body.get("context", {})
        esy  = ctx.get("esy", LATEST_SEASON)

        prices  = [{"feedstock": f, "price_inr_litre": p["price_inr_litre"], "effective_from": p["effective_from"]}
                   for f, p in EBP_PRICES.get(esy, {}).items()]
        blending = BLENDING_DATA.get(esy, {}).get("monthly", [])[:4]
        tenders  = [t for t in OMC_TENDERS if t["esy"] == esy]
        notifs   = sorted(CCEA_NOTIFICATIONS, key=lambda x: x["notification_date"], reverse=True)[:3]
        depots   = [d for d in OMC_DEPOTS if d["state"] == ctx.get("distillery_state", "")]

        system = f"""You are an expert analyst for India's Ethanol Blending Programme (EBP).
Answer ONLY based on the data below. Do NOT invent numbers. Max 4 paragraphs.

EBP PRICES (ESY {esy}): {json.dumps(prices)}
BLENDING DATA: {json.dumps(blending)}
TENDERS: {json.dumps(tenders)}
NOTIFICATIONS: {json.dumps(notifs)}
DEPOTS: {json.dumps(depots)}
CONTEXT: {json.dumps(ctx)}"""

        payload = json.dumps({
            "model": LLM_MODEL,
            "max_tokens": 800,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": query},
            ],
        }).encode()

        req = urllib.request.Request(
            LLM_ENDPOINT, data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {LLM_API_KEY}"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                llm_resp = json.loads(resp.read())
            analysis = llm_resp["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            return err(502, f"LLM error {e.code}: {e.read().decode()[:200]}")
        except Exception as e:
            return err(502, f"LLM call failed: {str(e)}")

        return ok({
            "query": query,
            "analysis": analysis,
            "llm_model": LLM_MODEL,
            "esy": esy,
            "disclaimer": "Based on PPAC/PIB/OMC public data. Not financial advice.",
        }, meta)

    def log_message(self, *args):
        pass
