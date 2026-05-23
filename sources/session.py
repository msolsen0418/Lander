"""Shared session factory — uses cloudscraper to bypass WAF/Cloudflare on target sites."""

import random
import cloudscraper

_PLATFORMS = ["windows", "darwin", "linux"]


def make_session():
    """Return a cloudscraper session that mimics a real Chrome browser."""
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": random.choice(_PLATFORMS),
            "mobile": False,
        }
    )
    return scraper
