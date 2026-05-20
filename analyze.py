"""
/api/v1/ethanol/analyze — LLM analysis endpoint
Passes embedded data to your own LLM. No Supabase reads for data.
Only Supabase used: API key validation (rate limiting).
"""

import json
import os
import hashlib
import urllib.request
import urllib.error
from datetime import date

from handlers import (
    EBP_PRICES, BLENDING_DATA, OMC_TENDERS,
    OMC_DEPOTS, CCEA_NOTIFICATIONS, LATEST_SEASON
)

LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "")
LLM_API_KEY  = os.environ.get("LLM_API_KEY", "")
LLM_MODEL    = os.environ.get("LLM_MODEL", "")


def validate_key(event, endpoint):
    from supabase import create_client
    qs = event.get("queryStringParameters") or {}
    hdrs = event.get("headers") or {}
    raw = qs.get("api_key") or hdrs.get("x-api-key") or hdrs.get("X-API-Key")
    if not raw: return False, "Missing API key.", None
    h = hashlib.sha256(raw.encode()).hexdigest()
    svc = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    rows = svc.table("api_keys").select("*").eq("key_hash", h).execute().data
    if not rows: return False, "Invalid API key.", None
    key = rows[0]
    if not key["is_active"]: return False, "Key inactive.", None
    today = date.today().isoformat()
    usage = svc.table("api_usage").select("*").eq("key_id", key["id"]).eq("usage_date", today).execute().data
    count = usage[0]["call_count"] if usage else 0
    if count >= key["daily_limit"]: return False, f"Daily limit reached.", None
    if usage:
        svc.table("api_usage").update({"call_count": count+1, "endpoint": endpoint}).eq("key_id", key["id"]).eq("usage_date", today).execute()
    else:
        svc.table("api_usage").insert({"key_id": key["id"], "usage_date": today, "call_count": 1, "endpoint": endpoint}).execute()
    return True, "OK", {"tier": key["tier"], "calls_remaining": key["daily_limit"] - count - 1}

def ok(data, meta=None):
    body = {"data": data, "status": 200}
    if meta: body["meta"] = meta
    return {"statusCode":200,"headers":{"Content-Type":"application/json","Access-Control-Allow-Origin":"*"},"body":json.dumps(body,default=str)}

def err(status, msg):
    return {"statusCode":status,"headers":{"Content-Type":"application/json","Access-Control-Allow-Origin":"*"},"body":json.dumps({"error":msg,"status":status})}


def handler(event, context):
    allowed, reason, meta = validate_key(event, "/v1/ethanol/analyze")
    if not allowed: return err(401, reason)
    if meta and meta.get("tier") == "free":
        return err(403, "AI analysis requires Starter tier. Upgrade at gridintelin.com/pricing")
    if not LLM_ENDPOINT:
        return err(503, "LLM endpoint not configured. Set LLM_ENDPOINT env var.")

    try: body = json.loads(event.get("body") or "{}")
    except: return err(400, "Invalid JSON body.")
    if not body.get("query"): return err(400, "Required: 'query' string")

    query = body["query"]
    ctx   = body.get("context", {})
    esy   = ctx.get("esy", LATEST_SEASON)

    # Pull directly from embedded data — zero DB reads
    prices   = [{"feedstock": f, **{k: v for k, v in p.items() if k != "prev"}}
                for f, p in EBP_PRICES.get(esy, {}).items()]
    blending = BLENDING_DATA.get(esy, {}).get("monthly", [])[:4]
    tenders  = [t for t in OMC_TENDERS if t["esy"] == esy]
    notifs   = sorted(CCEA_NOTIFICATIONS, key=lambda x: x["notification_date"], reverse=True)[:3]
    depots   = [d for d in OMC_DEPOTS if d["state"] == ctx.get("distillery_state", "")]

    system = f"""You are an expert analyst for India's Ethanol Blending Programme (EBP).

RULES:
- Answer ONLY based on the data below. Do NOT invent numbers.
- If data is missing, say so explicitly.
- Be direct, specific, actionable. Max 4 paragraphs.

=== LIVE EMBEDDED DATA (ESY {esy}) ===

EBP PRICES (CCEA-verified):
{json.dumps(prices, indent=2)}

BLENDING ACHIEVEMENT (PPAC data):
{json.dumps(blending, indent=2)}

OMC TENDERS:
{json.dumps(tenders, indent=2)}

LATEST NOTIFICATIONS:
{json.dumps(notifs, indent=2)}

DEPOTS IN {ctx.get('distillery_state','N/A')}:
{json.dumps(depots, indent=2)}

USER CONTEXT:
{json.dumps(ctx, indent=2)}
"""

    payload = json.dumps({
        "model": LLM_MODEL,
        "max_tokens": 800,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": query},
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

    return ok({"query": query, "analysis": analysis,
               "data_used": {"prices": len(prices), "blending_months": len(blending),
                             "tenders": len(tenders), "notifications": len(notifs)},
               "llm_model": LLM_MODEL, "esy": esy,
               "disclaimer": "Analysis based on PPAC/PIB/OMC public data. Not financial advice."}, meta)
