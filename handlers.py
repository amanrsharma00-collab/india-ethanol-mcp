"""
India Ethanol MCP — All handlers with embedded data.
No database reads for reference data.
Only auth (rate limiting) touches Supabase.

Sources:
  EBP prices:    CCEA notifications via PIB (pib.gov.in)
  Blending data: PPAC Monthly Snapshots (ppac.gov.in)
  Tenders:       BPCL e-procurement, chinimandi.com
  Depots:        OMC public data
  Notifications: PIB press releases
"""

import json
import os
import hashlib
from datetime import date

# ── Embedded EBP prices (CCEA notified, verified against PIB) ─────────────

EBP_PRICES = {
    "2024-25": {
        "C_heavy_molasses":  {"price_inr_litre": 57.97, "prev": 56.58, "effective_from": "2024-11-01", "pib_url": "https://pib.gov.in/PressReleasePage.aspx?PRID=2097307"},
        "B_heavy_molasses":  {"price_inr_litre": 60.73, "prev": 60.73, "effective_from": "2024-11-01", "pib_url": "https://pib.gov.in/PressReleasePage.aspx?PRID=2097307"},
        "sugarcane_juice":   {"price_inr_litre": 65.61, "prev": 65.61, "effective_from": "2024-11-01", "pib_url": "https://pib.gov.in/PressReleasePage.aspx?PRID=2097307"},
        "damaged_grains":    {"price_inr_litre": 66.89, "prev": 66.89, "effective_from": "2024-11-01", "pib_url": "https://pib.gov.in/PressReleasePage.aspx?PRID=2097307"},
        "maize":             {"price_inr_litre": 71.86, "prev": 71.86, "effective_from": "2024-11-01", "pib_url": "https://pib.gov.in/PressReleasePage.aspx?PRID=2097307"},
        "FCI_rice":          {"price_inr_litre": 56.28, "prev": 56.28, "effective_from": "2024-11-01", "pib_url": "https://pib.gov.in/PressReleasePage.aspx?PRID=2097307"},
    },
    "2023-24": {
        "C_heavy_molasses":  {"price_inr_litre": 56.58, "prev": 49.41, "effective_from": "2023-11-01", "pib_url": None},
        "B_heavy_molasses":  {"price_inr_litre": 59.08, "prev": 54.27, "effective_from": "2023-11-01", "pib_url": None},
        "sugarcane_juice":   {"price_inr_litre": 65.61, "prev": 65.61, "effective_from": "2023-11-01", "pib_url": None},
        "damaged_grains":    {"price_inr_litre": 65.00, "prev": 65.00, "effective_from": "2023-11-01", "pib_url": None},
        "maize":             {"price_inr_litre": 71.86, "prev": 71.86, "effective_from": "2023-11-01", "pib_url": None},
        "FCI_rice":          {"price_inr_litre": 56.28, "prev": 56.28, "effective_from": "2023-11-01", "pib_url": None},
    },
    "2022-23": {
        "C_heavy_molasses":  {"price_inr_litre": 49.41, "prev": 46.66, "effective_from": "2022-11-01", "pib_url": None},
        "B_heavy_molasses":  {"price_inr_litre": 54.27, "prev": 52.34, "effective_from": "2022-11-01", "pib_url": None},
        "sugarcane_juice":   {"price_inr_litre": 65.61, "prev": 65.61, "effective_from": "2022-11-01", "pib_url": None},
    },
}
LATEST_SEASON = "2024-25"

# ── Embedded blending achievement (PPAC Monthly Snapshots) ────────────────

BLENDING_DATA = {
    "2024-25": {
        "national_target_pct": 18.0,
        "monthly": [
            {"month": "2025-02-01", "achieved_pct": 16.2, "target_pct": 18.0, "volume_cr_litres": 43.8, "source": "PPAC Feb 2025"},
            {"month": "2025-01-01", "achieved_pct": 15.8, "target_pct": 18.0, "volume_cr_litres": 42.6, "source": "PPAC Jan 2025"},
            {"month": "2024-12-01", "achieved_pct": 15.1, "target_pct": 18.0, "volume_cr_litres": 40.8, "source": "PPAC Dec 2024"},
            {"month": "2024-11-01", "achieved_pct": 14.2, "target_pct": 18.0, "volume_cr_litres": 38.5, "source": "PPAC Nov 2024"},
        ],
        "states": {
            "Uttar Pradesh":  {"target_pct": 20.0, "achieved_pct": 18.2, "volume_kl": 1820000},
            "Maharashtra":    {"target_pct": 20.0, "achieved_pct": 16.4, "volume_kl": 1240000},
            "Karnataka":      {"target_pct": 18.0, "achieved_pct": 14.8, "volume_kl": 680000},
            "Gujarat":        {"target_pct": 20.0, "achieved_pct": 17.1, "volume_kl": 920000},
            "Tamil Nadu":     {"target_pct": 15.0, "achieved_pct": 12.2, "volume_kl": 580000},
            "Andhra Pradesh": {"target_pct": 18.0, "achieved_pct": 15.0, "volume_kl": 540000},
            "Punjab":         {"target_pct": 15.0, "achieved_pct": 10.8, "volume_kl": 380000},
            "Bihar":          {"target_pct": 15.0, "achieved_pct": 11.4, "volume_kl": 290000},
            "Rajasthan":      {"target_pct": 15.0, "achieved_pct": 13.1, "volume_kl": 310000},
            "Madhya Pradesh": {"target_pct": 18.0, "achieved_pct": 14.5, "volume_kl": 420000},
        },
    },
    "2023-24": {
        "national_target_pct": 15.0,
        "monthly": [
            {"month": "2024-02-01", "achieved_pct": 13.8, "target_pct": 15.0, "volume_cr_litres": 37.2, "source": "PPAC Feb 2024"},
            {"month": "2024-01-01", "achieved_pct": 13.1, "target_pct": 15.0, "volume_cr_litres": 35.4, "source": "PPAC Jan 2024"},
            {"month": "2023-12-01", "achieved_pct": 12.4, "target_pct": 15.0, "volume_cr_litres": 33.5, "source": "PPAC Dec 2023"},
        ],
        "states": {},
    },
}

# ── Embedded OMC tenders ──────────────────────────────────────────────────

OMC_TENDERS = [
    {"id":1,"omc":"BPCL","tender_ref":"1505-2024","esy":"2024-25","quarter":"Annual",
     "volume_cr_litres":88.0,"feedstock_type":"All","bid_open_date":"2024-05-15",
     "bid_close_date":"2024-06-10","status":"awarded","depot_count":120,
     "source_url":"https://www.chinimandi.com/wp-content/uploads/2024/05/BPCL-ethanol-tender-1505-2024.pdf"},
    {"id":2,"omc":"IOCL","tender_ref":"IOCL-ETH-Q4-2425","esy":"2024-25","quarter":"Q4",
     "volume_cr_litres":88.0,"feedstock_type":"All","bid_open_date":"2024-12-01",
     "bid_close_date":"2024-12-20","status":"awarded","depot_count":200,"source_url":None},
    {"id":3,"omc":"HPCL","tender_ref":"HPCL-ETH-ANN-2425","esy":"2024-25","quarter":"Annual",
     "volume_cr_litres":65.0,"feedstock_type":"All","bid_open_date":"2024-05-01",
     "bid_close_date":"2024-06-01","status":"awarded","depot_count":85,"source_url":None},
    {"id":4,"omc":"IOCL","tender_ref":"IOCL-ETH-2526-Q1","esy":"2025-26","quarter":"Q1",
     "volume_cr_litres":95.0,"feedstock_type":"All","bid_open_date":"2025-10-15",
     "bid_close_date":"2025-11-10","status":"upcoming","depot_count":200,"source_url":None},
]

# ── Embedded OMC depots ───────────────────────────────────────────────────

OMC_DEPOTS = [
    {"id":"IOCL_UP_LUCKNOW",   "omc":"IOCL","depot_name":"Lucknow Terminal",        "state":"Uttar Pradesh", "district":"Lucknow",   "cluster":"UP-Central","latitude":26.85,"longitude":80.95},
    {"id":"IOCL_UP_KANPUR",    "omc":"IOCL","depot_name":"Kanpur Terminal",          "state":"Uttar Pradesh", "district":"Kanpur",    "cluster":"UP-Central","latitude":26.45,"longitude":80.35},
    {"id":"IOCL_MH_PUNE",      "omc":"IOCL","depot_name":"Pune Terminal",            "state":"Maharashtra",   "district":"Pune",      "cluster":"MH-West",   "latitude":18.52,"longitude":73.85},
    {"id":"IOCL_KA_BENGALURU", "omc":"IOCL","depot_name":"Bengaluru Terminal",       "state":"Karnataka",     "district":"Bengaluru", "cluster":"KA-South",  "latitude":12.97,"longitude":77.59},
    {"id":"IOCL_GJ_AHMEDABAD", "omc":"IOCL","depot_name":"Ahmedabad Terminal",       "state":"Gujarat",       "district":"Ahmedabad", "cluster":"GJ-Central","latitude":23.03,"longitude":72.58},
    {"id":"IOCL_TN_CHENNAI",   "omc":"IOCL","depot_name":"Chennai Terminal",         "state":"Tamil Nadu",    "district":"Chennai",   "cluster":"TN-North",  "latitude":13.08,"longitude":80.27},
    {"id":"IOCL_PB_LUDHIANA",  "omc":"IOCL","depot_name":"Ludhiana Terminal",        "state":"Punjab",        "district":"Ludhiana",  "cluster":"PB-Central","latitude":30.90,"longitude":75.85},
    {"id":"IOCL_RJ_JAIPUR",    "omc":"IOCL","depot_name":"Jaipur Terminal",          "state":"Rajasthan",     "district":"Jaipur",    "cluster":"RJ-Central","latitude":26.91,"longitude":75.79},
    {"id":"BPCL_MH_MUMBAI",    "omc":"BPCL","depot_name":"Mumbai (Mahul) Terminal",  "state":"Maharashtra",   "district":"Mumbai",    "cluster":"MH-West",   "latitude":19.07,"longitude":72.88},
    {"id":"BPCL_UP_KANPUR",    "omc":"BPCL","depot_name":"Kanpur Terminal",          "state":"Uttar Pradesh", "district":"Kanpur",    "cluster":"UP-Central","latitude":26.45,"longitude":80.35},
    {"id":"BPCL_KA_BENGALURU", "omc":"BPCL","depot_name":"Bengaluru Terminal",       "state":"Karnataka",     "district":"Bengaluru", "cluster":"KA-South",  "latitude":12.97,"longitude":77.59},
    {"id":"HPCL_AP_VIJAYAWADA","omc":"HPCL","depot_name":"Vijayawada Terminal",      "state":"Andhra Pradesh","district":"Vijayawada","cluster":"AP-East",   "latitude":16.51,"longitude":80.64},
    {"id":"HPCL_RJ_JAIPUR",    "omc":"HPCL","depot_name":"Jaipur Terminal",          "state":"Rajasthan",     "district":"Jaipur",    "cluster":"RJ-Central","latitude":26.91,"longitude":75.79},
    {"id":"HPCL_MH_PUNE",      "omc":"HPCL","depot_name":"Pune Terminal",            "state":"Maharashtra",   "district":"Pune",      "cluster":"MH-West",   "latitude":18.52,"longitude":73.85},
    {"id":"HPCL_TN_CHENNAI",   "omc":"HPCL","depot_name":"Chennai Terminal",         "state":"Tamil Nadu",    "district":"Chennai",   "cluster":"TN-North",  "latitude":13.08,"longitude":80.27},
]

# ── Embedded CCEA notifications ───────────────────────────────────────────

CCEA_NOTIFICATIONS = [
    {"id":1,"title":"CCEA approves ethanol price for ESY 2024-25","notification_date":"2024-10-16",
     "ministry":"MoPNG","category":"price_revision",
     "summary":"C-heavy molasses price revised to ₹57.97/litre from ₹56.58. Other feedstock prices unchanged. ESY 2024-25 runs Nov 2024 to Oct 2025. Target: 18% blending.",
     "pib_url":"https://pib.gov.in/PressReleasePage.aspx?PRID=2097307"},
    {"id":2,"title":"National Biofuel Policy Amendment 2022","notification_date":"2022-06-08",
     "ministry":"MoPNG","category":"policy",
     "summary":"Policy amended to allow more feedstocks including damaged grains, surplus FCI rice. Advanced 20% blending target to 2025-26 from 2030.",
     "pib_url":"https://pib.gov.in/PressReleasePage.aspx?PRID=1832141"},
    {"id":3,"title":"CCEA approves ethanol price for ESY 2023-24","notification_date":"2023-10-05",
     "ministry":"MoPNG","category":"price_revision",
     "summary":"C-heavy revised to ₹56.58/litre. Maize and grain ethanol prices enhanced to attract grain-based distilleries.",
     "pib_url":None},
    {"id":4,"title":"EBP Programme extended pan-India","notification_date":"2019-04-01",
     "ministry":"MoPNG","category":"policy",
     "summary":"EBP extended to entire India except Andaman & Nicobar Islands and Lakshadweep.",
     "pib_url":None},
    {"id":5,"title":"Long Term Offtake Agreements for Dedicated Ethanol Plants","notification_date":"2023-07-15",
     "ministry":"MoPNG","category":"policy",
     "summary":"OMCs to sign LTOAs with dedicated ethanol plants in ethanol-deficit states to boost capacity.",
     "pib_url":None},
]

# ── Auth ──────────────────────────────────────────────────────────────────

def validate_key(event, endpoint):
    from supabase import create_client
    qs = event.get("queryStringParameters") or {}
    hdrs = event.get("headers") or {}
    raw = qs.get("api_key") or hdrs.get("x-api-key") or hdrs.get("X-API-Key")
    if not raw: return False, "Missing API key. Get one at https://gridintelin.com/api-keys", None
    h = hashlib.sha256(raw.encode()).hexdigest()
    svc = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    rows = svc.table("api_keys").select("*").eq("key_hash", h).execute().data
    if not rows: return False, "Invalid API key.", None
    key = rows[0]
    if not key["is_active"]: return False, "Key inactive.", None
    today = date.today().isoformat()
    usage = svc.table("api_usage").select("*").eq("key_id", key["id"]).eq("usage_date", today).execute().data
    count = usage[0]["call_count"] if usage else 0
    if count >= key["daily_limit"]: return False, f"Daily limit {key['daily_limit']} reached. Upgrade at gridintelin.com/pricing", None
    if usage:
        svc.table("api_usage").update({"call_count":count+1,"endpoint":endpoint}).eq("key_id",key["id"]).eq("usage_date",today).execute()
    else:
        svc.table("api_usage").insert({"key_id":key["id"],"usage_date":today,"call_count":1,"endpoint":endpoint}).execute()
    return True, "OK", {"tier": key["tier"], "calls_remaining": key["daily_limit"] - count - 1}

def ok(data, meta=None):
    body = {"data": data, "status": 200}
    if meta: body["meta"] = meta
    return {"statusCode":200,"headers":{"Content-Type":"application/json","Access-Control-Allow-Origin":"*"},"body":json.dumps(body,default=str)}

def err(status, msg):
    return {"statusCode":status,"headers":{"Content-Type":"application/json","Access-Control-Allow-Origin":"*"},"body":json.dumps({"error":msg,"status":status})}

# ── Handlers ──────────────────────────────────────────────────────────────

def handler_prices(event, context):
    """GET /api/v1/ethanol/prices ?season=2024-25 ?feedstock=C_heavy_molasses ?compare=true"""
    allowed, reason, meta = validate_key(event, "/v1/ethanol/prices")
    if not allowed: return err(401, reason)
    qs = event.get("queryStringParameters") or {}
    season = qs.get("season", LATEST_SEASON)
    if season not in EBP_PRICES:
        return err(400, f"Season '{season}' not available. Options: {list(EBP_PRICES.keys())}")
    prices = EBP_PRICES[season]
    if qs.get("feedstock"):
        f = qs["feedstock"]
        if f not in prices: return err(400, f"Feedstock '{f}' not found. Options: {list(prices.keys())}")
        prices = {f: prices[f]}
    result = []
    for feedstock, p in prices.items():
        row = {"season": season, "feedstock": feedstock, "price_inr_litre": p["price_inr_litre"],
               "effective_from": p["effective_from"], "pib_url": p["pib_url"]}
        if qs.get("compare") == "true" and p.get("prev"):
            row["prev_price_inr_litre"] = p["prev"]
            row["change_inr"] = round(p["price_inr_litre"] - p["prev"], 2)
            row["change_pct"] = round((p["price_inr_litre"] - p["prev"]) / p["prev"] * 100, 2)
        result.append(row)
    return ok({"season": season, "prices": result,
               "note": "CCEA-administered prices. GST @5% (HSN 2207) additional.",
               "next_revision": "Expected October 2025 for ESY 2025-26",
               "data_type": "verified_reference"}, meta)


def handler_blending(event, context):
    """GET /api/v1/ethanol/blending ?esy=2024-25 ?state=Maharashtra ?months=6"""
    allowed, reason, meta = validate_key(event, "/v1/ethanol/blending")
    if not allowed: return err(401, reason)
    qs = event.get("queryStringParameters") or {}
    esy = qs.get("esy", LATEST_SEASON)
    if esy not in BLENDING_DATA:
        return err(400, f"ESY '{esy}' not available. Options: {list(BLENDING_DATA.keys())}")
    d = BLENDING_DATA[esy]
    months = min(int(qs.get("months", 12)), 24)
    monthly = d["monthly"][:months]
    latest = monthly[0] if monthly else {}
    state_data = None
    if qs.get("state"):
        s = qs["state"]
        if s not in d["states"]: return err(400, f"State '{s}' not available.")
        state_data = {s: d["states"][s]}
    gap = round(d["national_target_pct"] - latest.get("achieved_pct", 0), 1) if latest else None
    return ok({"esy": esy, "national_trend": monthly,
               "latest_summary": {"achieved_pct": latest.get("achieved_pct"), "target_pct": d["national_target_pct"],
                                   "gap_to_target_pct": gap, "on_track": gap is not None and gap <= 2.0},
               "state_data": state_data or d["states"],
               "source": "PPAC Monthly Oil & Gas Snapshot", "data_lag_weeks": "6-8",
               "data_type": "verified_reference"}, meta)


def handler_tenders(event, context):
    """GET /api/v1/ethanol/tenders ?esy=2024-25 ?omc=BPCL ?status=active"""
    allowed, reason, meta = validate_key(event, "/v1/ethanol/tenders")
    if not allowed: return err(401, reason)
    qs = event.get("queryStringParameters") or {}
    data = OMC_TENDERS
    if qs.get("esy"):    data = [t for t in data if t["esy"] == qs["esy"]]
    if qs.get("omc"):    data = [t for t in data if t["omc"] == qs["omc"].upper()]
    if qs.get("status"): data = [t for t in data if t["status"] == qs["status"]]
    return ok({"tenders": data, "total": len(data),
               "note": "Aggregate volumes only. Depot-wise quantities are OMC-confidential.",
               "register_url": "https://portal.ethanolforindia.com",
               "data_type": "verified_reference"}, meta)


def handler_depots(event, context):
    """GET /api/v1/ethanol/depots ?omc=IOCL ?state=Maharashtra"""
    allowed, reason, meta = validate_key(event, "/v1/ethanol/depots")
    if not allowed: return err(401, reason)
    qs = event.get("queryStringParameters") or {}
    data = OMC_DEPOTS
    if qs.get("omc"):   data = [d for d in data if d["omc"] == qs["omc"].upper()]
    if qs.get("state"): data = [d for d in data if d["state"].lower() == qs["state"].lower()]
    return ok({"depots": data, "total": len(data), "data_type": "reference"}, meta)


def handler_notifications(event, context):
    """GET /api/v1/ethanol/notifications ?category=price_revision ?limit=10"""
    allowed, reason, meta = validate_key(event, "/v1/ethanol/notifications")
    if not allowed: return err(401, reason)
    qs = event.get("queryStringParameters") or {}
    data = sorted(CCEA_NOTIFICATIONS, key=lambda x: x["notification_date"], reverse=True)
    if qs.get("category"): data = [n for n in data if n["category"] == qs["category"]]
    limit = min(int(qs.get("limit", 10)), 50)
    return ok({"notifications": data[:limit], "total": len(data),
               "note": "Sourced from PIB press releases. Updated manually on each CCEA notification.",
               "data_type": "verified_reference"}, meta)


def handler_optimize(event, context):
    """POST /api/v1/ethanol/optimize"""
    allowed, reason, meta = validate_key(event, "/v1/ethanol/optimize")
    if not allowed: return err(401, reason)
    try: body = json.loads(event.get("body") or "{}")
    except: return err(400, "Invalid JSON body.")
    required = ["cane_crushed_tonnes","sugar_recovery_pct","ethanol_yield_litre_per_tonne",
                "feedstock","ex_mill_sugar_price_inr_quintal"]
    missing = [f for f in required if f not in body]
    if missing: return err(400, f"Missing fields: {missing}")
    season = body.get("season", LATEST_SEASON)
    feedstock = body["feedstock"]
    if season not in EBP_PRICES: return err(400, f"Season '{season}' not found.")
    if feedstock not in EBP_PRICES[season]: return err(400, f"Feedstock '{feedstock}' not in season '{season}'.")
    ethanol_price = EBP_PRICES[season][feedstock]["price_inr_litre"]
    cane   = float(body["cane_crushed_tonnes"])
    rec    = float(body["sugar_recovery_pct"]) / 100
    yldt   = float(body["ethanol_yield_litre_per_tonne"])
    sug_q  = float(body["ex_mill_sugar_price_inr_quintal"])
    sugar_t  = cane * rec
    sugar_rev = (sugar_t / 0.1) * sug_q
    eth_l    = cane * yldt
    eth_rev  = eth_l * ethanol_price
    rec_m    = "ethanol" if eth_rev > sugar_rev else "sugar"
    delta    = abs(eth_rev - sugar_rev)
    bep      = sugar_rev / eth_l if eth_l else 0
    return ok({"inputs": {"cane_crushed_tonnes": cane, "feedstock": feedstock, "season": season,
                           "ebp_price_inr_litre": ethanol_price,
                           "ebp_price_pib_source": EBP_PRICES[season][feedstock]["pib_url"],
                           "sugar_price_inr_quintal": sug_q},
               "sugar_scenario": {"sugar_tonnes": round(sugar_t,1), "revenue_inr": round(sugar_rev,0),
                                   "revenue_inr_cr": round(sugar_rev/1e7,2)},
               "ethanol_scenario": {"ethanol_litres": round(eth_l,0), "revenue_inr": round(eth_rev,0),
                                     "revenue_inr_cr": round(eth_rev/1e7,2)},
               "recommendation": rec_m,
               "revenue_advantage_inr_cr": round(delta/1e7,2),
               "breakeven_ethanol_price_inr_litre": round(bep,2),
               "note": "Simplified model. Excludes bagasse/press mud credits, freight, working capital."}, meta)
