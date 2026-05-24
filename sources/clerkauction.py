"""
Scraper for the Grant Street Group ClerkAuction platform.

Several Florida counties — including Palm Beach and St. Lucie — use
ClerkAuction instead of RealForeclose for their online foreclosure and
tax-deed auctions.  Each county gets its own subdomain:
  https://mypalmbeachclerk.clerkauction.com/
  https://stlucie.clerkauction.com/

The calendar pages are server-side rendered and require no JavaScript,
so a plain requests session works fine.
"""

import re
import time
import logging
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .session import make_direct_session

logger = logging.getLogger(__name__)

# (county_name, base_url, auction_type)
_COUNTIES = [
    ("Palm Beach", "https://mypalmbeachclerk.clerkauction.com", "foreclosure"),
    ("Palm Beach", "https://mypalmbeachclerk.clerkauction.com", "tax_deed"),
    ("St. Lucie",  "https://stlucie.clerkauction.com",          "foreclosure"),
    ("St. Lucie",  "https://stlucie.clerkauction.com",          "tax_deed"),
]

_CALENDAR_PATHS = {
    "foreclosure": "/calendar/foreclosures",
    "tax_deed":    "/calendar/taxdeeds",
}


def scrape(progress_cb=None) -> list[dict]:
    """Scrape upcoming auction listings from ClerkAuction counties."""
    session = make_direct_session()
    all_listings: list[dict] = []
    seen: set[str] = set()

    for i, (county_name, base_url, auction_type) in enumerate(_COUNTIES):
        if progress_cb:
            progress_cb(f"ClerkAuction: {county_name} ({auction_type})", i, len(_COUNTIES))
        try:
            path = _CALENDAR_PATHS[auction_type]
            listings = _scrape_calendar(session, base_url, path, county_name, auction_type)
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


def _scrape_calendar(session, base_url: str, path: str, county_name: str, auction_type: str) -> list[dict]:
    url = base_url + path
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    return _parse_calendar(soup, base_url, county_name, auction_type)


def _parse_calendar(soup: BeautifulSoup, base_url: str, county_name: str, auction_type: str) -> list[dict]:
    listings = []

    date_blocks = soup.select("div.auction-date-group, div.sales-date, section.auction-group")
    if not date_blocks:
        date_blocks = [soup]

    for block in date_blocks:
        date_raw = ""
        for hdr in block.select("h2, h3, h4, .date-header, .auction-date"):
            t = hdr.get_text(strip=True)
            if re.search(r"\d{1,2}/\d{1,2}/\d{4}|\w+ \d{1,2},?\s*\d{4}", t):
                date_raw = t
                break

        rows = block.select("tr") or block.select("li.auction-item, div.auction-item, div.case-row")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                cells = [row]
            if len(cells) < 2:
                continue

            text_vals = [c.get_text(separator=" ", strip=True) for c in cells]
            full_text = " ".join(text_vals)

            case_number = _extract_case(full_text)
            if not case_number:
                continue

            address_raw = _extract_address(text_vals, cells)
            bid_raw = _extract_bid(text_vals)
            sale_date = _parse_date(date_raw) or _parse_date(_extract_date_from_text(full_text))

            detail_url = None
            for cell in cells:
                a = cell.find("a", href=True)
                if a:
                    href = a["href"]
                    detail_url = href if href.startswith("http") else urljoin(base_url, href)
                    break

            address, city, zip_code = _split_address(address_raw)
            if not address and not case_number:
                continue

            listings.append({
                "address": address or full_text[:80],
                "city": city,
                "county": county_name,
                "state": "FL",
                "zip": zip_code,
                "auction_type": auction_type,
                "opening_bid": _parse_dollar(bid_raw),
                "sale_date": sale_date,
                "case_number": case_number.strip(),
                "source_url": detail_url or base_url + _CALENDAR_PATHS[auction_type],
                "source": "clerkauction",
            })

    return listings


# ── helpers ────────────────────────────────────────────────────────────────────────────

def _extract_case(text: str) -> str:
    m = re.search(r"\b(\d{4}[\-\s](?:CA|CC|SC|CF|TD|FC)[\-\s]\d+(?:[\-\s]\d+)?)\b", text, re.I)
    if m:
        return re.sub(r"\s+", "-", m.group(1).strip().upper())
    m2 = re.search(r"\b(\d{2}[-]\d{4}[-]\w+)\b", text)
    return m2.group(1) if m2 else ""


def _extract_address(text_vals: list[str], cells) -> str:
    for val in text_vals:
        if re.search(r"\d{2,5}\s+[A-Za-z]", val) and len(val) > 10:
            return val
    return ""


def _extract_bid(text_vals: list[str]) -> str:
    for val in text_vals:
        if "$" in val and re.search(r"\d", val):
            return val
    return ""


def _extract_date_from_text(text: str) -> str:
    m = re.search(r"\d{1,2}/\d{1,2}/\d{4}", text)
    return m.group(0) if m else ""


def _parse_dollar(s: str) -> float | None:
    s = re.sub(r"[^\d.]", "", s)
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _parse_date(s: str) -> str | None:
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y",
                "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s or None


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
