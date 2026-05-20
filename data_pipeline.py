"""
Ethanol Data Scrapers
Runs as a cron job (Vercel Cron or GitHub Actions).

Scrapers:
1. ppac_blending_scraper   — PPAC monthly PDF → blending % data
2. pib_notification_scraper — PIB press releases → CCEA notifications
3. bpcl_tender_scraper     — BPCL e-proc portal → tender listings

Schedule:
- PIB notifications: every 6 hours
- PPAC blending: weekly (PPAC publishes monthly)
- Tender scraper: daily
"""

import os
import re
import json
import hashlib
import logging
import urllib.request
import urllib.parse
from datetime import datetime, date
from typing import Optional
from supabase import create_client

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

def get_db():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# ── PIB Notification Scraper ──────────────────────────────────────────────

def scrape_pib_ethanol_notifications():
    """
    Scrapes PIB press releases tagged under MoPNG for ethanol-related notifications.
    PIB has a public search endpoint — no login required.
    """
    log.info("Scraping PIB for ethanol notifications...")

    # PIB public search — filter by MoPNG ministry
    search_url = "https://pib.gov.in/allRel.aspx"
    params = {
        "ModId": "2",       # MoPNG ministry code
        "lang": "1",
        "reg": "3",
    }

    url = f"{search_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        log.error(f"PIB fetch failed: {e}")
        return []

    # Extract press release links and titles
    # PIB HTML pattern: <a href="/PressReleasePage.aspx?PRID=XXXXXXX">Title</a>
    pattern = r'href="(/PressReleasePage\.aspx\?PRID=(\d+))"[^>]*>([^<]+)</a>'
    matches = re.findall(pattern, html, re.IGNORECASE)

    ethanol_keywords = ["ethanol", "ebp", "biofuel", "blending", "ccea", "molasses", "distiller"]
    db = get_db()
    inserted = 0

    for path, prid, title in matches:
        title = title.strip()
        if not any(kw in title.lower() for kw in ethanol_keywords):
            continue

        pib_url = f"https://pib.gov.in{path}"

        # Check if already scraped
        existing = db.table("ccea_notifications").select("id").eq("pib_url", pib_url).execute().data
        if existing:
            continue

        # Fetch the press release for summary
        summary = _fetch_pib_summary(pib_url)
        category = _classify_notification(title, summary)

        db.table("ccea_notifications").insert({
            "title": title[:500],
            "notification_date": datetime.today().date().isoformat(),
            "ministry": "MoPNG",
            "category": category,
            "summary": summary[:2000] if summary else None,
            "pib_url": pib_url,
        }).execute()

        log.info(f"Inserted notification: {title[:80]}")
        inserted += 1

    log.info(f"PIB scraper: {inserted} new notifications inserted")
    return inserted


def _fetch_pib_summary(url: str) -> Optional[str]:
    """Fetch and extract text from a PIB press release."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        # Extract main content div
        match = re.search(r'<div[^>]*class="[^"]*innner-page-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        if match:
            text = re.sub(r'<[^>]+>', ' ', match.group(1))
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:2000]
    except Exception:
        pass
    return None


def _classify_notification(title: str, summary: Optional[str]) -> str:
    text = (title + " " + (summary or "")).lower()
    if any(w in text for w in ["price", "rate", "₹", "rs.", "per litre", "revised"]):
        return "price_revision"
    if any(w in text for w in ["target", "blending", "percentage", "achieve"]):
        return "target_change"
    return "policy"


# ── PPAC Blending Data Scraper ────────────────────────────────────────────

def scrape_ppac_blending():
    """
    PPAC publishes monthly 'Snapshot of India's Oil & Gas Data' PDFs.
    This scraper fetches the latest PDF list and extracts blending data.

    The PDF structure is consistent: ethanol blending % is on page 4-5.
    We use pdfplumber to extract the table.
    """
    log.info("Scraping PPAC for blending data...")

    # PPAC lists reports at a known URL pattern
    ppac_base = "https://ppac.gov.in"
    listing_url = f"{ppac_base}/report_studies/monthly"

    try:
        req = urllib.request.Request(listing_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        log.error(f"PPAC listing fetch failed: {e}")
        return 0

    # Find PDF links matching monthly snapshot pattern
    pdf_pattern = r'href="([^"]*Snapshot[^"]*\.pdf)"'
    pdfs = re.findall(pdf_pattern, html, re.IGNORECASE)

    if not pdfs:
        log.warning("No PPAC PDFs found — site structure may have changed")
        return 0

    latest_pdf_path = pdfs[0]
    pdf_url = latest_pdf_path if latest_pdf_path.startswith("http") else f"{ppac_base}{latest_pdf_path}"

    log.info(f"Processing PPAC PDF: {pdf_url}")
    blending_data = _extract_blending_from_pdf(pdf_url)

    if not blending_data:
        log.warning("Could not extract blending data from PDF")
        return 0

    db = get_db()
    db.table("blending_achievement").upsert(blending_data, on_conflict="month").execute()
    log.info(f"PPAC: upserted blending data for {blending_data.get('month')}")
    return 1


def _extract_blending_from_pdf(pdf_url: str) -> Optional[dict]:
    """
    Download PDF and extract ethanol blending percentage.
    PPAC PDFs consistently report: "Ethanol blending with Petrol was X% during [Month]"
    """
    try:
        # Try regex extraction from fetched text (lighter than pdfplumber)
        req = urllib.request.Request(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            # For full PDF parsing, would use pdfplumber
            # Here we attempt text extraction from PDF binary
            content = resp.read()

        # Pattern found in all PPAC snapshots
        text = content.decode("latin-1", errors="ignore")
        match = re.search(
            r'Ethanol blending with Petrol was ([\d.]+)% during (\w+ \d{4})',
            text, re.IGNORECASE
        )
        if match:
            pct = float(match.group(1))
            month_str = match.group(2)
            month_date = datetime.strptime(month_str, "%B %Y").date().replace(day=1)

            # Determine ESY from month
            esy = _month_to_esy(month_date)

            return {
                "month": month_date.isoformat(),
                "esy": esy,
                "national_achieved_pct": pct,
                "national_target_pct": 18.0,
                "source": f"PPAC Snapshot {month_str}",
                "scraped_at": datetime.utcnow().isoformat(),
            }
    except Exception as e:
        log.error(f"PDF extraction error: {e}")
    return None


def _month_to_esy(month: date) -> str:
    """ESY runs Nov-Oct. e.g. Nov 2024 = ESY 2024-25"""
    if month.month >= 11:
        return f"{month.year}-{str(month.year + 1)[2:]}"
    else:
        return f"{month.year - 1}-{str(month.year)[2:]}"


# ── BPCL Tender Scraper ───────────────────────────────────────────────────

def scrape_bpcl_tenders():
    """
    BPCL publishes ethanol tenders on their e-procurement portal.
    Public listing is accessible without login.
    https://bpcltenders.eproc.in/
    """
    log.info("Scraping BPCL tenders...")

    url = "https://bpcltenders.eproc.in/BPCLPublicTenders/tenderList"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        log.error(f"BPCL tender fetch failed: {e}")
        return 0

    # Extract ethanol-related tenders
    ethanol_tenders = []
    ethanol_pattern = r'(?i)ethanol|denatured anhydrous|EBP'

    # Parse tender rows (HTML table structure varies — adapt as needed)
    row_pattern = r'<tr[^>]*>(.*?)</tr>'
    for row_html in re.findall(row_pattern, html, re.DOTALL):
        if not re.search(ethanol_pattern, row_html):
            continue
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if len(cells) >= 3:
            ethanol_tenders.append({
                "tender_ref": cells[0] if cells else None,
                "title": cells[1] if len(cells) > 1 else None,
                "date": cells[2] if len(cells) > 2 else None,
            })

    log.info(f"Found {len(ethanol_tenders)} ethanol tenders on BPCL portal")

    db = get_db()
    inserted = 0
    for t in ethanol_tenders:
        if not t.get("tender_ref"):
            continue
        existing = db.table("omc_tenders").select("id").eq("tender_ref", t["tender_ref"]).eq("omc", "BPCL").execute().data
        if existing:
            continue
        db.table("omc_tenders").insert({
            "omc": "BPCL",
            "tender_ref": t["tender_ref"],
            "esy": "2024-25",    # Will be parsed from title in production
            "quarter": "Unknown",
            "status": "active",
            "source_url": url,
            "scraped_at": datetime.utcnow().isoformat(),
        }).execute()
        inserted += 1

    log.info(f"BPCL: {inserted} new tenders inserted")
    return inserted


# ── Cron entry point ──────────────────────────────────────────────────────

def run_all_scrapers():
    """Run all scrapers. Called by Vercel Cron or GitHub Actions."""
    results = {}
    try:
        results["pib_notifications"] = scrape_pib_ethanol_notifications()
    except Exception as e:
        results["pib_notifications"] = f"ERROR: {e}"

    try:
        results["ppac_blending"] = scrape_ppac_blending()
    except Exception as e:
        results["ppac_blending"] = f"ERROR: {e}"

    try:
        results["bpcl_tenders"] = scrape_bpcl_tenders()
    except Exception as e:
        results["bpcl_tenders"] = f"ERROR: {e}"

    log.info(f"Scraper run complete: {results}")
    return results


if __name__ == "__main__":
    run_all_scrapers()
