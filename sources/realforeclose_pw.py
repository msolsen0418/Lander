"""
Playwright-based scraper for RealForeclose.com.

Uses a real headless Chromium browser to bypass bot detection / Cloudflare
challenges that block datacenter and residential proxy IPs.

Falls back gracefully if Playwright is not installed.
"""

import re
import time
import logging
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

from .realforeclose import (
    BASE_URL,
    parse_county_list,
    _parse_auction_table,
)

logger = logging.getLogger(__name__)

# Required args for headless Chromium inside a container (no sandbox, no GPU)
_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--single-process",
]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def is_available() -> bool:
    return _AVAILABLE


def scrape(max_counties: int = None, progress_cb=None) -> list[dict]:
    """Drop-in replacement for realforeclose.scrape() using Playwright."""
    if not _AVAILABLE:
        raise RuntimeError("playwright package not installed")

    all_listings = []
    counties = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=_LAUNCH_ARGS)
        ctx = browser.new_context(
            user_agent=_UA,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = ctx.new_page()
        page.set_default_timeout(30_000)

        try:
            logger.info("Playwright: opening RealForeclose.com")
            page.goto(BASE_URL + "/", wait_until="networkidle")
            counties = parse_county_list(BeautifulSoup(page.content(), "lxml"))
            logger.info("Playwright: found %d counties", len(counties))

            if max_counties:
                counties = counties[:max_counties]

            for i, (county_id, county_name, auction_type) in enumerate(counties):
                if progress_cb:
                    progress_cb(county_name, i, len(counties))
                try:
                    listings = _scrape_county(page, county_id, county_name, auction_type)
                    all_listings.extend(listings)
                    logger.info("  %s: %d listings", county_name, len(listings))
                except Exception as exc:
                    logger.warning("Failed %s (id=%s): %s", county_name, county_id, exc)
                time.sleep(0.5)

        finally:
            browser.close()

    if progress_cb:
        progress_cb("Done", len(counties), len(counties))

    return all_listings


def _scrape_county(page, county_id: str, county_name: str, default_type: str) -> list[dict]:
    url = f"{BASE_URL}/index.cfm?zaction=COUNTY&Zmethod=PREVIEW&COUNTYID={county_id}"
    page.goto(url, wait_until="networkidle")

    listings = []
    page_num = 1

    while True:
        soup = BeautifulSoup(page.content(), "lxml")
        page_listings = _parse_auction_table(soup, county_name, default_type, county_id)
        listings.extend(page_listings)

        next_link = soup.select_one("a.PageNext, a[title='Next Page'], a:-soup-contains('Next')")
        if not next_link or not page_listings:
            break
        next_href = next_link.get("href", "")
        if not next_href or next_href == "#":
            break

        page_num += 1
        if page_num > 20:
            break

        next_url = (
            next_href if next_href.startswith("http")
            else BASE_URL + "/" + next_href.lstrip("/")
        )
        page.goto(next_url, wait_until="networkidle")
        time.sleep(0.3)

    return listings
