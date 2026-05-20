# india-ethanol-mcp

> India's first MCP server and API for Ethanol Blending Programme intelligence.  
> Live CCEA prices, OMC tender data, blending achievement tracking, and AI-powered market analysis.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-HTTP-blue)](https://modelcontextprotocol.io)

---

## What this is

A hosted MCP server + REST API that gives AI agents and developers programmatic access to Indian ethanol market data — data that currently exists only in government PDFs, press releases, and OMC procurement portals.

**No more manually monitoring PIB for CCEA price revisions.**  
**No more downloading PPAC PDFs to track blending percentages.**  
**No more Excel models for sugar vs ethanol economics.**

---

## MCP Tools (7 tools)

| Tool | What it does |
|------|-------------|
| `get_ebp_prices` | Current CCEA-notified procurement prices by feedstock |
| `get_blending_achievement` | Monthly national + state blending % vs target |
| `get_omc_tenders` | IOCL/BPCL/HPCL tender listings and status |
| `get_omc_depots` | Depot locations for freight zone planning |
| `get_ccea_notifications` | Policy/price notifications scraped from PIB |
| `optimize_sugar_vs_ethanol` | Revenue comparison using live CCEA prices |
| `analyze_ethanol_market` | **AI analysis layer** — ask strategic questions |

---

## Quickstart

### Claude Desktop (HTTP MCP)

```json
{
  "mcpServers": {
    "india-ethanol": {
      "type": "http",
      "url": "https://ethanol.gridintelin.com/api/mcp",
      "headers": { "X-API-Key": "iem_YOUR_KEY_HERE" }
    }
  }
}
```

Get a free API key: **https://gridintelin.com/api-keys**  
Free tier: 50 calls/day.

---

## REST API

Base URL: `https://ethanol.gridintelin.com`

### GET /api/v1/ethanol/prices

```bash
# All feedstocks, current season
curl "https://ethanol.gridintelin.com/api/v1/ethanol/prices?api_key=YOUR_KEY"

# Specific feedstock with price change comparison
curl "https://ethanol.gridintelin.com/api/v1/ethanol/prices?feedstock=C_heavy_molasses&compare=true&api_key=YOUR_KEY"
```

**Response:**
```json
{
  "data": {
    "prices": [
      {
        "season": "2024-25",
        "feedstock": "C_heavy_molasses",
        "price_inr_litre": 57.97,
        "previous_price_inr_litre": 56.58,
        "price_change_inr": 1.39,
        "price_change_pct": 2.46,
        "effective_from": "2024-11-01",
        "ccea_notification_date": "2024-10-16",
        "pib_url": "https://pib.gov.in/PressReleasePage.aspx?PRID=2097307"
      }
    ],
    "note": "Prices as notified by CCEA. GST @5% applicable additionally.",
    "next_revision": "Expected October 2025 for ESY 2025-26"
  }
}
```

### GET /api/v1/ethanol/blending

```bash
curl "https://ethanol.gridintelin.com/api/v1/ethanol/blending?esy=2024-25&api_key=YOUR_KEY"
```

### GET /api/v1/ethanol/tenders

```bash
curl "https://ethanol.gridintelin.com/api/v1/ethanol/tenders?omc=BPCL&esy=2024-25&api_key=YOUR_KEY"
```

> ⚠️ Depot-wise allocation quantities are OMC-confidential. Aggregate volumes only. For actual bidding: [portal.ethanolforindia.com](https://portal.ethanolforindia.com)

### GET /api/v1/ethanol/depots

```bash
curl "https://ethanol.gridintelin.com/api/v1/ethanol/depots?state=Uttar+Pradesh&api_key=YOUR_KEY"
```

### GET /api/v1/ethanol/notifications

```bash
# Latest CCEA notifications
curl "https://ethanol.gridintelin.com/api/v1/ethanol/notifications?category=price_revision&api_key=YOUR_KEY"
```

### POST /api/v1/ethanol/optimize

```bash
curl -X POST "https://ethanol.gridintelin.com/api/v1/ethanol/optimize?api_key=YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "cane_crushed_tonnes": 100000,
    "sugar_recovery_pct": 10.5,
    "ethanol_yield_litre_per_tonne": 72,
    "feedstock": "B_heavy_molasses",
    "ex_mill_sugar_price_inr_quintal": 3600,
    "season": "2024-25"
  }'
```

**Response:**
```json
{
  "data": {
    "recommendation": "ethanol",
    "sugar_scenario": { "revenue_inr_cr": 37.8 },
    "ethanol_scenario": { "revenue_inr_cr": 43.7 },
    "revenue_advantage_inr_cr": 5.9,
    "breakeven_ethanol_price_inr_litre": 52.5
  }
}
```

### POST /api/v1/ethanol/analyze ⭐ *Starter tier+*

The AI layer. Grounds Claude Sonnet on your actual live data and answers strategic questions.

```bash
curl -X POST "https://ethanol.gridintelin.com/api/v1/ethanol/analyze?api_key=YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Should I bid on UP cluster tenders this ESY given current B-heavy prices?",
    "context": {
      "distillery_state": "Uttar Pradesh",
      "feedstock": "B_heavy_molasses",
      "capacity_klpd": 100,
      "esy": "2024-25"
    }
  }'
```

Returns a 3-5 paragraph analytical response grounded on live CCEA prices, blending data, and tender information. Not generic advice — data-driven analysis.

---

## Data sources and freshness

| Data | Source | Update frequency |
|------|--------|-----------------|
| EBP prices | CCEA via PIB press releases | Within 24hrs of notification |
| CCEA notifications | PIB.gov.in | Every 6 hours |
| Blending achievement | PPAC Monthly Snapshot PDFs | Weekly (PPAC publishes monthly) |
| OMC tenders | BPCL e-procurement portal | Daily |
| Depot locations | OMC public data | Quarterly |

**What is NOT available (honestly):**
- Depot-wise offtake volumes — OMC internal data
- Individual distillery allocation quantities — confidential
- Real-time tender bid status — requires OMC portal login

---

## Rate limits

| Tier | Calls/day | Analyze endpoint | Price |
|------|-----------|-----------------|-------|
| Free | 50 | ❌ | Free |
| Starter | 1,000 | ✅ | ₹5K/month |
| Pro | Unlimited | ✅ | ₹20K/month |

---

## Self-hosted deployment

```bash
git clone https://github.com/gridintelin/india-ethanol-mcp
cd india-ethanol-mcp
cp .env.example .env    # fill in credentials
pip install -r requirements.txt
python scrapers/data_pipeline.py   # seed initial data
vercel deploy
```

---

## Who is this for

- **Distillery CFOs and procurement teams** — monitor CCEA prices, plan tender bids
- **Sugar mills** — optimize diversion decisions using live prices
- **Energy/commodity analysts** — programmatic access to blending data
- **Developers building ethanol sector tools** — use as data infrastructure

---

## Related

- [india-energy-mcp](https://github.com/gridintelin/india-energy-mcp) — Power grid MCP
- [oasse-sdk](https://github.com/gridintelin/oasse-sdk) — Open access settlement SDK
- [GridIntel India](https://gridintelin.com) — Full platform

## License
MIT
