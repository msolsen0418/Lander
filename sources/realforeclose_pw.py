"""
Scraper for RealForeclose.com county-specific auction sites.

Each Florida county that uses the RealAuction/RealForeclose platform has its
own subdomain:  https://<county>.realforeclose.com/

The auction listing data is loaded via an AJAX JSON endpoint, so no Playwright
is needed. This module keeps its original name and function signature so the
rest of the codebase (scraper.py, tests) doesn't need changes.

Falls back gracefully if Playwright is not installed (it is not needed).
"""

import re
import time
import logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from .session import make_direct_session

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

logger = logging.getLogger(__name__)

# Florida counties on the RealForeclose / RealAuction platform.
# Each entry is (subdomain, county_name, auction_type).
# Subdomains were validated to resolve in DNS as of May 2026.
_FLORIDA_COUNTIES = [
    ("alachua",      "Alachua",      "foreclosure"),
    ("alachua",      "Alachua",      "tax_deed"),
    ("bay",          "Bay",          "foreclosure"),
    ("bay",          "Bay",          "tax_deed"),
    ("broward",      "Broward",      "foreclosure"),
    ("charlotte",    "Charlotte",    "foreclosure"),
    ("citrus",       "Citrus",       "foreclosure"),
    ("citrus",       "Citrus",       "tax_deed"),
    ("clay",         "Clay",         "foreclosure"),
    ("clay",         "Clay",         "tax_deed"),
    ("duval",        "Duval",        "foreclosure"),
    ("duval",        "Duval",        "tax_deed"),
    ("escambia",     "Escambia",     "foreclosure"),
    ("escambia",     "Escambia",     "tax_deed"),
    ("flagler",      "Flagler",      "foreclosure"),
    ("flagler",      "Flagler",      "tax_deed"),
    ("hillsborough", "Hillsborough", "foreclosure"),
    ("hillsborough", "Hillsborough", "tax_deed"),
    ("indian-river", "Indian River", "foreclosure"),
    ("indian-river", "Indian River", "tax_deed"),
    ("lee",          "Lee",          "foreclosure"),
    ("lee",          "Lee",          "tax_deed"),
    ("leon",         "Leon",         "foreclosure"),
    ("leon",         "Leon",         "tax_deed"),
    ("manatee",      "Manatee",      "foreclosure"),
    ("marion",       "Marion",       "foreclosure"),
    ("marion",       "Marion",       "tax_deed"),
    ("martin",       "Martin",       "foreclosure"),
    ("martin",       "Martin",       "tax_deed"),
    ("miamidade",    "Miami-Dade",   "foreclosure"),
    ("orange",       "Orange",       "foreclosure"),
    ("orange",       "Orange",       "tax_deed"),
    ("palmbeach",    "Palm Beach",   "foreclosure"),
    ("palmbeach",    "Palm Beach",   "tax_deed"),
    ("pasco",        "Pasco",        "foreclosure"),
    ("pasco",        "Pasco",        "tax_deed"),
    ("pinellas",     "Pinellas",     "foreclosure"),
    ("pinellas",     "Pinellas",     "tax_deed"),
    ("polk",         "Polk",         "foreclosure"),
    ("polk",         "Polk",         "tax_deed"),
    ("sarasota",     "Sarasota",     "foreclosure"),
    ("sarasota",     "Sarasota",     "tax_deed"),
    ("stlucie",      "St. Lucie",    "foreclosure"),
    ("stlucie",      "St. Lucie",    "tax_deed"),
    ("volusia",      "Volusia",      "foreclosure"),
    ("volusia",      "Volusia",      "tax_deed"),
]

# How many future auction dates to fetch per county (keeps run time reasonable)
_MAX_DATES_PER_COUNTY = 4


def is_available() -> bool:
    """Always True — this module no longer requires Playwright."""
    return True


def scrape(max_counties: int = None, progress_cb=None) -> list[dict]:
    """
    Scrape upcoming auction listings from Florida county RealForeclose sites.

    Uses the site's JSON AJAX endpoint directly — no browser required.

    Args:
        max_counties: Limit number of county/type combinations (for testing).
        progress_cb:  Optional callable(label, done, total) for progress.
    Returns:
        List of property dicts ready for database.upsert_property().
    """
    session = make_direct_session()
    all_listings: list[dict] = []
    seen: set[str] = set()

    counties = _FLORIDA_COUNTIES
    if max_counties:
        counties = counties[:max_counties]

    for i, (subdomain, county_name, auction_type) in enumerate(counties):
        if progress_cb:
            progress_cb(f"{county_name} ({auction_type})", i, len(counties))
        try:
            listings = _scrape_county(session, subdomain, county_name, auction_type)
            for lst in listings:
                key = lst["case_number"]
                if key not in seen:
                    seen.add(key)
                    all_listings.append(lst)
            logger.info("RealForeclose %s %s: %d listings", county_name, auction_type, len(listings))
        except Exception as exc:
            logger.warning("RealForeclose %s %s failed: %s", county_name, auction_type, exc)
        time.sleep(0.5)

    if progress_cb:
        progress_cb("Done", len(counties), len(counties))

    logger.info("RealForeclose total: %d listings", len(all_listings))
    return all_listings


# ── per-county scraping ─────────────────────────────────────────────

def _scrape_county(session, subdomain: str, county_name: str, auction_type: str) -> list[dict]:
    """Collect all upcoming auction listings for one county/type pair."""
    base_url = f"https://{subdomain}.realforeclose.com"
    listings: list[dict] = []

    # 1. Load the calendar page to get session cookies and discover upcoming dates
    calendar_url = f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW"
    resp = session.get(calendar_url, timeout=20)
    resp.raise_for_status()

    auction_dates = _discover_auction_dates(resp.text, base_url)
    if not auction_dates:
        # No upcoming dates visible — still try to load today's data
        auction_dates = [None]

    for auction_date in auction_dates[:_MAX_DATES_PER_COUNTY]:
        if auction_date:
            date_url = f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AuctionDate={auction_date}"
            session.get(date_url, timeout=20)  # set session date context

        page_listings = _fetch_auction_area(session, base_url, county_name, auction_type)
        listings.extend(page_listings)
        time.sleep(0.3)

    return listings


def _discover_auction_dates(html: str, base_url: str) -> list[str]:
    """Parse auction date strings from the calendar navigation HTML."""
    soup = BeautifulSoup(html, "lxml")
    dates: list[str] = []
    nav = soup.find(class_="AuctionNav_Main")
    if not nav:
        return dates
    for a in nav.find_all("a", href=True):
        m = re.search(r"AuctionDate=(\d{2}/\d{2}/\d{4})", a["href"])
        if m:
            d = m.group(1)
            if d not in dates:
                dates.append(d)
    return dates


def _fetch_auction_area(session, base_url: str, county_name: str, auction_type: str) -> list[dict]:
    """Call the AJAX update endpoint and parse returned auction items."""
    tx = int(time.time() * 1000)
    ajax_url = (
        f"{base_url}/index.cfm"
        f"?zaction=AUCTION&Zmethod=UPDATE&FNC=LOAD&AREA=W"
        f"&PageDir=0&doR=1&tx={tx}&bypassPage=0"
    )
    resp = session.get(ajax_url, timeout=20)
    resp.raise_for_status()

    try:
        data = resp.json()
    except Exception:
        logger.debug("Non-JSON response from %s", ajax_url)
        return []

    raw_html = data.get("retHTML", "")
    if not raw_html:
        return []

    decoded = _decode_rf_html(raw_html)
    soup = BeautifulSoup(decoded, "lxml")
    items = soup.find_all("div", class_="AUCTION_ITEM")

    listings = []
    for item in items:
        lst = _parse_auction_item(item, base_url, county_name, auction_type)
        if lst:
            listings.append(lst)
    return listings


def _decode_rf_html(rh: str) -> str:
    """Reverse the server-side HTML compression used in the JSON response."""
    rh = rh.replace("@A", '<div class="')
    rh = rh.replace("@B", "</div>")
    rh = rh.replace("@C", 'class="')
    rh = rh.replace("@D", "<div>")
    rh = rh.replace("@E", "AUCTION")
    rh = rh.replace("@F", "</td><td")
    rh = rh.replace("@G", "</td></tr>")
    rh = rh.replace("@H", "<tr><td ")
    rh = rh.replace("@I", "table")
    rh = rh.replace("@J", 'p_back="NextCheck=')
    rh = rh.replace("@K", 'style="Display:none"')
    rh = rh.replace("@L", "/index.cfm?zaction=auction&zmethod=details&AID=")
    return rh


def _parse_auction_item(item, base_url: str, county_name: str, auction_type: str) -> dict | None:
    """Extract a property listing dict from one AUCTION_ITEM div."""
    fields: dict[str, str] = {}
    # The city/state/zip continuation row has an empty label cell.
    last_labeled_key = ""
    city_zip_raw = ""

    for row in item.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) == 2:
            label = cells[0].get_text(strip=True).rstrip(":").lower()
            value = cells[1].get_text(strip=True)
            if label:
                fields[label] = value
                last_labeled_key = label
            elif last_labeled_key == "property address" and value:
                city_zip_raw = value

    case_number = fields.get("case #", "").strip()
    if not case_number:
        return None

    address_raw = fields.get("property address", "")
    bid_raw = fields.get("final judgment amount", "") or fields.get("opening bid", "")
    atype_raw = fields.get("auction type", auction_type)

    # Map auction type string
    atype = auction_type
    if "tax" in atype_raw.lower():
        atype = "tax_deed"
    elif "foreclos" in atype_raw.lower():
        atype = "foreclosure"

    # Detail URL
    aid = item.get("aid", "")
    detail_url = f"{base_url}/index.cfm?zaction=auction&zmethod=details&AID={aid}" if aid else base_url

    city, zip_code = _parse_city_zip(city_zip_raw)

    return {
        "address": address_raw.strip() or case_number,
        "city": city,
        "county": county_name,
        "state": "FL",
        "zip": zip_code,
        "auction_type": atype,
        "opening_bid": _parse_dollar(bid_raw),
        "sale_date": None,   # date is in the session context, not per-item
        "case_number": case_number,
        "source_url": detail_url,
        "source": "realforeclose",
    }


# ── helpers ─────────────────────────────────────────────────

def _parse_city_zip(raw: str) -> tuple[str, str]:
    """Parse 'CITY, FL- 33414' or 'CITY FL 33414' into (city, zip)."""
    raw = raw.strip()
    m = re.match(r"^([^,]+?)[\s,]+FL[-\s]*(\d{5})?", raw, re.IGNORECASE)
    if m:
        return m.group(1).strip().title(), (m.group(2) or "")
    m2 = re.search(r"(\d{5})", raw)
    zip_code = m2.group(1) if m2 else ""
    city = re.sub(r"[,\s]*FL.*", "", raw, flags=re.IGNORECASE).strip().title()
    return city, zip_code


def _parse_dollar(s: str) -> float | None:
    s = re.sub(r"[^\d.]", "", s or "")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _split_address(raw: str) -> tuple[str, str, str]:
    m = re.match(r"^(.+?),\s*(.+?),?\s*FL\s*(\d{5})?", raw, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip(), (m.group(3) or "")
    m2 = re.search(r"(\d{5})$", raw)
    zip_code = m2.group(1) if m2 else ""
    parts = raw.rsplit(",", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip(), zip_code
    return raw.strip(), "", zip_code
