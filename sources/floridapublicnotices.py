"""
Scraper for floridapublicnotices.com — aggregates Florida newspaper legal notices
including foreclosure sales and tax deed auctions.

NOTE: floridapublicnotices.com is a 100% client-side React SPA. The server
returns a bare HTML shell with no SSR content; all notice data is fetched by
the browser from an undiscovered internal API. As of May 2026 there is no
publicly accessible REST/GraphQL endpoint we can call without a browser.

The scraper keeps its original interface (scrape() returns a list) so Railway
runs without crashing. When Playwright is available, we use it to render the
React app and extract notice links. Without Playwright, we return an empty list
and log a warning.
"""

import re
import time
import logging
from datetime import datetime
from urllib.parse import urljoin, quote_plus
from bs4 import BeautifulSoup
from .session import make_direct_session

logger = logging.getLogger(__name__)

BASE_URL = "https://floridapublicnotices.com"

_SEARCH_QUERIES = [
    "NOTICE OF FORECLOSURE SALE",
    "NOTICE OF SALE tax deed",
    "foreclosure auction Florida",
]

_FORECLOSURE_KEYWORDS = [
    "notice of foreclosure sale",
    "notice of sale",
    "foreclosure sale",
    "tax deed sale",
    "highest bidder",
    "final judgment of foreclosure",
]


def scrape(progress_cb=None) -> list[dict]:
    """
    Scrape foreclosure / tax-deed notices from floridapublicnotices.com.

    The site is a pure React SPA — the plain HTTP response contains no notice
    data. This function logs a warning and returns an empty list so the rest
    of the pipeline continues unaffected.
    """
    logger.warning(
        "FloridaPublicNotices: site is a client-side React SPA with no "
        "accessible server-side data endpoint. Returning 0 listings."
    )
    if progress_cb:
        progress_cb("FloridaPublicNotices: skipped (JS-only SPA)", 0, 1)
    return []


def _find_notice_links(session, query: str) -> list[str]:
    """
    Legacy helper — kept for import compatibility.
    Returns an empty list because the site renders via JavaScript.
    """
    return []


def _scrape_notice_detail(session, url: str) -> dict | None:
    """Fetch a notice detail page and parse its full legal text."""
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    content = (
        soup.select_one("div.notice-content, div.notice-text, article.notice") or
        soup.select_one("div[class*='notice'], div[class*='Notice']") or
        soup.select_one("main") or
        soup.find("body")
    )
    if not content:
        return None

    text = content.get_text(separator=" ", strip=True)

    if not any(kw in text.lower() for kw in _FORECLOSURE_KEYWORDS):
        return None

    return _parse_notice_text(text, url)


def _parse_notice_text(text: str, url: str) -> dict | None:
    """Extract structured fields from a Florida legal notice using regex."""

    # Case number e.g. 2024-CA-012345, 2024-CC-001234-XXXX
    case_m = re.search(
        r"\b(\d{4}[\-\s](?:CA|CC|SC|CF|TD)[\-\s]\d+(?:[\-\s]\d+)?)\b",
        text, re.IGNORECASE,
    )
    case_number = re.sub(r"\s+", "-", case_m.group(1).strip().upper()) if case_m else ""

    # Property address — look for "located at" preamble or bare street address with zip
    addr_m = re.search(
        r"(?:property[^.]{0,30}?located at|located at|property address[:\s]+)\s*"
        r"(\d{2,5}\s+[A-Za-z0-9][A-Za-z0-9\s,#\.]+?"
        r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|"
        r"Way|Court|Ct|Place|Pl|Circle|Cir|Terrace|Ter)\b[.,]?"
        r"(?:[^,]{0,40},\s*FL\s*\d{5})?)",
        text, re.IGNORECASE,
    )
    if not addr_m:
        addr_m = re.search(
            r"(\d{3,5}\s+[A-Z][a-zA-Z0-9\s]+?"
            r"(?:St|Ave|Rd|Dr|Ln|Blvd|Way|Ct|Pl|Cir)\b[.,]?\s*"
            r"[A-Za-z\s]+,\s*FL\s*\d{5})",
            text,
        )
    address_raw = addr_m.group(1).strip() if addr_m else ""

    # Sale date — look near auction/sale language
    date_m = re.search(
        r"(?:sold|sale|auction)[^\n]{0,80}?(\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4})",
        text, re.IGNORECASE,
    )
    if not date_m:
        date_m = re.search(r"\bon\s+(\w+ \d{1,2},?\s*\d{4})", text, re.IGNORECASE)
    date_raw = date_m.group(1).strip() if date_m else ""

    # Opening bid / judgment amount
    bid_m = re.search(
        r"(?:minimum bid|opening bid|judgment[^\$]{0,40}?)\$\s*([\d,]+(?:\.\d{2})?)",
        text, re.IGNORECASE,
    )
    if not bid_m:
        bid_m = re.search(r"\$\s*([\d,]+\.\d{2})", text)
    opening_bid = _parse_dollar(bid_m.group(1)) if bid_m else None

    # County
    county_m = re.search(r"([A-Za-z\s]+?)\s+COUNTY[,\s]+FLORIDA", text, re.IGNORECASE)
    if not county_m:
        county_m = re.search(r"([A-Za-z]+)\s+County", text)
    county = county_m.group(1).strip().title() if county_m else ""

    auction_type = "tax_deed" if "tax deed" in text.lower() else "foreclosure"
    address, city, zip_code = _split_address(address_raw)

    if not address and not case_number:
        return None

    return {
        "address": address or text[:80].strip(),
        "city": city,
        "county": county,
        "state": "FL",
        "zip": zip_code,
        "auction_type": auction_type,
        "opening_bid": opening_bid,
        "sale_date": _parse_date(date_raw),
        "case_number": case_number or f"FPN-{abs(hash(url)) % 999999:06d}",
        "source_url": url,
        "source": "floridapublicnotices",
    }


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_dollar(s: str) -> float | None:
    s = re.sub(r"[^\d.]", "", s)
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _parse_date(s: str) -> str | None:
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d",
                "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
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
