"""
Scraper for Florida county auction sites on the RealAuction / RealForeclose platform.

Palm Beach and St. Lucie counties (originally targeted via clerkauction.com
subdomains that no longer resolve) now host their auctions at:
  https://palmbeach.realforeclose.com/
  https://stlucie.realforeclose.com/

The auction listing data is loaded via a JSON AJAX endpoint — no Playwright needed.
"""

import re
import time
import logging
from bs4 import BeautifulSoup
from .session import make_direct_session

logger = logging.getLogger(__name__)

# (county_name, subdomain, auction_type)
# These two counties were the original ClerkAuction targets.
_COUNTIES = [
    ("Palm Beach", "palmbeach", "foreclosure"),
    ("Palm Beach", "palmbeach", "tax_deed"),
    ("St. Lucie",  "stlucie",  "foreclosure"),
    ("St. Lucie",  "stlucie",  "tax_deed"),
]

# How many upcoming auction dates to scrape per county/type
_MAX_DATES = 4


def scrape(progress_cb=None) -> list[dict]:
    """Scrape upcoming auction listings for Palm Beach and St. Lucie counties."""
    session = make_direct_session()
    all_listings: list[dict] = []
    seen: set[str] = set()

    for i, (county_name, subdomain, auction_type) in enumerate(_COUNTIES):
        if progress_cb:
            progress_cb(f"ClerkAuction: {county_name} ({auction_type})", i, len(_COUNTIES))
        try:
            listings = _scrape_county(session, subdomain, county_name, auction_type)
            for lst in listings:
                key = lst["case_number"]
                if key not in seen:
                    seen.add(key)
                    all_listings.append(lst)
            logger.info("ClerkAuction %s %s: %d listings", county_name, auction_type, len(listings))
        except Exception as exc:
            logger.warning("ClerkAuction %s %s failed: %s", county_name, auction_type, exc)
        time.sleep(1.0)

    return all_listings


# ── per-county scraping ───────────────────────────────────────────────────────

def _scrape_county(session, subdomain: str, county_name: str, auction_type: str) -> list[dict]:
    """Collect upcoming auction listings for one county/type via AJAX."""
    base_url = f"https://{subdomain}.realforeclose.com"

    # Load calendar page to establish session cookies and find upcoming dates
    calendar_url = f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW"
    resp = session.get(calendar_url, timeout=20)
    resp.raise_for_status()

    auction_dates = _discover_auction_dates(resp.text)
    if not auction_dates:
        auction_dates = [None]  # try with current date context

    listings: list[dict] = []
    for auction_date in auction_dates[:_MAX_DATES]:
        if auction_date:
            date_url = f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AuctionDate={auction_date}"
            session.get(date_url, timeout=20)  # set date context in session

        batch = _fetch_auction_area(session, base_url, county_name, auction_type)
        listings.extend(batch)
        time.sleep(0.3)

    return listings


def _discover_auction_dates(html: str) -> list[str]:
    """Extract upcoming auction date strings from the calendar nav HTML."""
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
    """Call the AJAX endpoint and parse auction items from the JSON response."""
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
    """Reverse the server-side HTML compression in the AJAX JSON response."""
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
    """Extract a structured listing dict from one AUCTION_ITEM div."""
    fields: dict[str, str] = {}
    # Track rows so we can read the unlabeled city/state/zip row that follows
    # the "Property Address:" row (the site leaves the label cell blank).
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
                # Unlabeled row immediately after address = "CITY, FL- ZIP"
                city_zip_raw = value

    case_number = fields.get("case #", "").strip()
    if not case_number:
        return None

    address_raw = fields.get("property address", "")
    bid_raw = fields.get("final judgment amount", "") or fields.get("opening bid", "")
    atype_raw = fields.get("auction type", auction_type)

    atype = auction_type
    if "tax" in atype_raw.lower():
        atype = "tax_deed"
    elif "foreclos" in atype_raw.lower():
        atype = "foreclosure"

    aid = item.get("aid", "")
    detail_url = f"{base_url}/index.cfm?zaction=auction&zmethod=details&AID={aid}" if aid else base_url

    # Parse city and zip from the unlabeled continuation row, e.g. "WELLINGTON, FL- 33414"
    city, zip_code = _parse_city_zip(city_zip_raw)

    return {
        "address": address_raw.strip() or case_number,
        "city": city,
        "county": county_name,
        "state": "FL",
        "zip": zip_code,
        "auction_type": atype,
        "opening_bid": _parse_dollar(bid_raw),
        "sale_date": None,
        "case_number": case_number,
        "source_url": detail_url,
        "source": "clerkauction",
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_city_zip(raw: str) -> tuple[str, str]:
    """Parse 'CITY, FL- 33414' or 'CITY FL 33414' into (city, zip)."""
    raw = raw.strip()
    # Strip trailing dash variants before zip
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
