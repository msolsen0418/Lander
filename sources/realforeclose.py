"""
Scraper for RealForeclose.com — the primary online auction platform used by
most Florida counties for tax deed and foreclosure sales.
"""

import re
import time
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from .session import make_session

logger = logging.getLogger(__name__)

BASE_URL = "https://www.realforeclose.com"

AUCTION_TYPE_MAP = {
    "tax deed": "tax_deed",
    "taxdeed": "tax_deed",
    "foreclosure": "foreclosure",
    "clerk": "foreclosure",
}


def scrape(max_counties: int = None, progress_cb=None) -> list[dict]:
    """
    Scrape upcoming Florida auction listings from RealForeclose.com.

    Args:
        max_counties: Limit number of counties (useful for testing).
        progress_cb: Optional callable(county_name, done, total) for progress.
    Returns:
        List of property dicts ready for database.upsert_property().
    """
    session = make_session()
    counties = _discover_counties(session)
    if max_counties:
        counties = counties[:max_counties]

    all_listings = []
    for i, (county_id, county_name, auction_type) in enumerate(counties):
        if progress_cb:
            progress_cb(county_name, i, len(counties))
        try:
            listings = _scrape_county(session, county_id, county_name, auction_type)
            all_listings.extend(listings)
            logger.info("  %s: %d listings", county_name, len(listings))
        except Exception as exc:
            logger.warning("Failed to scrape %s (id=%s): %s", county_name, county_id, exc)
        time.sleep(1.0)

    if progress_cb:
        progress_cb("Done", len(counties), len(counties))

    return all_listings


def _discover_counties(session) -> list[tuple]:
    """
    Returns list of (county_id, county_name, auction_type) from the
    RealForeclose homepage navigation.
    """
    resp = session.get(BASE_URL + "/", timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    unique = parse_county_list(soup)
    logger.info("Discovered %d county auction queues on RealForeclose", len(unique))
    return unique


def parse_county_list(soup: BeautifulSoup) -> list[tuple]:
    """Parse (county_id, county_name, auction_type) from a RealForeclose homepage soup.

    Exported so the Playwright scraper can reuse it without a requests session.
    """
    counties = []
    # The site has dropdown menus: "Tax Deed Sales" and "Foreclosure Sales"
    # Each menu item is a link like /index.cfm?zaction=COUNTY&Zmethod=PREVIEW&COUNTYID=XX
    for link in soup.select("a[href*='COUNTYID']"):
        href = link.get("href", "")
        m = re.search(r"COUNTYID=(\d+)", href, re.IGNORECASE)
        if not m:
            continue
        county_id = m.group(1)
        county_name = link.get_text(strip=True)
        if not county_name:
            continue

        parent_text = ""
        parent = link.find_parent("li")
        if parent:
            grandparent = parent.find_parent("ul")
            if grandparent:
                prev = grandparent.find_previous_sibling()
                if prev:
                    parent_text = prev.get_text(strip=True).lower()

        auction_type = "foreclosure"
        for key, val in AUCTION_TYPE_MAP.items():
            if key in parent_text or key in href.lower():
                auction_type = val
                break

        counties.append((county_id, county_name, auction_type))

    seen = set()
    unique = []
    for item in counties:
        if item[0] not in seen:
            seen.add(item[0])
            unique.append(item)

    return unique


def _scrape_county(session, county_id: str, county_name: str, default_type: str) -> list[dict]:
    """Scrape all upcoming auction listings for one county."""
    url = f"{BASE_URL}/index.cfm?zaction=COUNTY&Zmethod=PREVIEW&COUNTYID={county_id}"
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    listings = []
    # Results may be paginated; handle multiple pages
    page = 1
    while True:
        page_listings = _parse_auction_table(soup, county_name, default_type, county_id)
        listings.extend(page_listings)

        # Check for next page link
        next_link = soup.select_one("a.PageNext, a[title='Next Page'], a:-soup-contains('Next')")
        if not next_link or not page_listings:
            break
        next_href = next_link.get("href", "")
        if not next_href or next_href == "#":
            break

        page += 1
        if page > 20:  # safety cap
            break
        next_url = next_href if next_href.startswith("http") else BASE_URL + "/" + next_href.lstrip("/")
        resp = session.get(next_url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        time.sleep(0.5)

    return listings


def _parse_auction_table(soup: BeautifulSoup, county_name: str, default_type: str, county_id: str) -> list[dict]:
    """Parse the auction listing table from a county page."""
    listings = []

    # RealForeclose uses a table with class "DATAVIEW" or similar
    table = soup.select_one("table.DATAVIEW, table#DataGrid1, table.auctions")
    if not table:
        # Fallback: look for any table with auction data signals
        for t in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
            if any(h in headers for h in ["case #", "address", "opening bid", "sale date"]):
                table = t
                break

    if not table:
        return listings

    rows = table.find_all("tr")
    if not rows:
        return listings

    # Map column names to indices
    header_row = rows[0]
    headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

    col = {
        "case": _find_col(headers, ["case #", "case#", "case no", "case number"]),
        "address": _find_col(headers, ["address", "property address", "property"]),
        "bid": _find_col(headers, ["opening bid", "opening amount", "bid", "starting bid", "minimum bid"]),
        "date": _find_col(headers, ["sale date", "auction date", "date", "scheduled"]),
        "type": _find_col(headers, ["type", "sale type", "auction type"]),
    }

    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        try:
            listing = _parse_row(cells, col, county_name, default_type, county_id)
            if listing:
                listings.append(listing)
        except Exception as exc:
            logger.debug("Row parse error: %s", exc)

    return listings


def _parse_row(cells: list, col: dict, county_name: str, default_type: str, county_id: str) -> dict | None:
    def cell_text(idx):
        if idx is None or idx >= len(cells):
            return ""
        return cells[idx].get_text(separator=" ", strip=True)

    case_number = cell_text(col["case"]) or ""
    address_raw = cell_text(col["address"]) or ""
    bid_raw = cell_text(col["bid"]) or ""
    date_raw = cell_text(col["date"]) or ""
    type_raw = cell_text(col["type"]) or ""

    if not address_raw or address_raw.lower() in ("address", "property address"):
        return None

    opening_bid = _parse_dollar(bid_raw)
    sale_date = _parse_date(date_raw)
    address, city, zip_code = _split_address(address_raw)

    auction_type = default_type
    for key, val in AUCTION_TYPE_MAP.items():
        if key in type_raw.lower():
            auction_type = val
            break

    # Build a stable case number even if the site doesn't provide one
    if not case_number:
        case_number = f"RF-{county_id}-{address[:30]}"

    # Find detail URL
    detail_url = None
    for cell in cells:
        link = cell.find("a", href=True)
        if link:
            href = link["href"]
            detail_url = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
            break

    return {
        "address": address,
        "city": city,
        "county": county_name,
        "state": "FL",
        "zip": zip_code,
        "auction_type": auction_type,
        "opening_bid": opening_bid,
        "sale_date": sale_date,
        "case_number": case_number.strip(),
        "source_url": detail_url or f"{BASE_URL}/index.cfm?zaction=COUNTY&Zmethod=PREVIEW&COUNTYID={county_id}",
        "source": "realforeclose",
    }


# ── helpers ──────────────────────────────────────────────────────────────────

def _find_col(headers: list[str], candidates: list[str]) -> int | None:
    for candidate in candidates:
        for i, h in enumerate(headers):
            if candidate in h:
                return i
    return None


def _parse_dollar(s: str) -> float | None:
    s = re.sub(r"[^\d.]", "", s)
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _parse_date(s: str) -> str | None:
    """Try several common date formats; return ISO string or None."""
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s or None


def _split_address(raw: str) -> tuple[str, str, str]:
    """
    Attempt to split 'street, city, FL zip' into components.
    Returns (street, city, zip).
    """
    # Try: "123 Main St, Miami, FL 33101"
    m = re.match(r"^(.+?),\s*(.+?),?\s*FL\s*(\d{5})?", raw, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip(), (m.group(3) or "")

    # Try: last 5 digits = zip
    m2 = re.search(r"(\d{5})$", raw)
    zip_code = m2.group(1) if m2 else ""
    parts = raw.rsplit(",", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip(), zip_code

    return raw.strip(), "", zip_code
