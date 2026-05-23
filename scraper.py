"""
Orchestration module: runs all scrapers, enriches with valuations,
and persists results to the database.

Can be invoked directly (python scraper.py) or from the Flask app.
"""

import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import database as db
from sources import realforeclose
from valuations import zillow, redfin, county_appraiser

logger = logging.getLogger(__name__)

# Global scrape state (thread-safe via lock)
_state_lock = threading.Lock()
_scrape_state = {
    "running": False,
    "phase": "idle",
    "current": "",
    "done": 0,
    "total": 0,
    "errors": [],
    "last_completed": None,
}


def get_state() -> dict:
    with _state_lock:
        return dict(_scrape_state)


def _set_state(**kwargs):
    with _state_lock:
        _scrape_state.update(kwargs)


def run_full_scrape(max_counties: int = None):
    """
    Full pipeline:
      1. Scrape auction listings from RealForeclose.com
      2. For each new/updated property, fetch valuations from all sources
      3. Persist everything to SQLite

    Designed to be called in a background thread.
    """
    if _scrape_state["running"]:
        logger.warning("Scrape already in progress — skipping")
        return

    _set_state(running=True, phase="auctions", current="Connecting to RealForeclose.com...",
               done=0, total=0, errors=[])

    try:
        # ── Phase 1: Auction listings ──────────────────────────────────────
        logger.info("Phase 1: Scraping auction listings")

        def progress_cb(county_name, done, total):
            _set_state(current=county_name, done=done, total=total)

        listings = realforeclose.scrape(max_counties=max_counties, progress_cb=progress_cb)
        logger.info("Found %d listings total", len(listings))

        property_ids = []
        for listing in listings:
            try:
                pid = db.upsert_property(listing)
                property_ids.append((pid, listing))
            except Exception as exc:
                logger.warning("Failed to save listing %s: %s", listing.get("address"), exc)

        # ── Phase 2: Valuations ────────────────────────────────────────────
        logger.info("Phase 2: Fetching valuations for %d properties", len(property_ids))
        _set_state(phase="valuations", done=0, total=len(property_ids))

        for i, (pid, listing) in enumerate(property_ids):
            _set_state(current=listing.get("address", ""), done=i, total=len(property_ids))
            _enrich_property(pid, listing)
            time.sleep(0.5)  # be polite

        _set_state(phase="idle", running=False, current="", done=len(property_ids),
                   total=len(property_ids), last_completed=time.time())
        logger.info("Scrape complete.")

    except Exception as exc:
        logger.error("Scrape failed: %s", exc, exc_info=True)
        _set_state(running=False, phase="error", current=str(exc))


def _enrich_property(property_id: int, listing: dict):
    """Fetch all valuation sources for a single property (parallel requests)."""
    address = listing.get("address", "")
    city = listing.get("city", "")
    county = listing.get("county", "")
    zip_code = listing.get("zip", "")
    state = listing.get("state", "FL")

    tasks = {
        "county": lambda: county_appraiser.get_assessed_value(address, city, county, zip_code),
        "zillow": lambda: zillow.get_zestimate(address, city, state, zip_code),
        "redfin": lambda: redfin.get_estimate(address, city, state, zip_code),
    }

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fn): source for source, fn in tasks.items()}
        for future in as_completed(futures):
            source = futures[future]
            try:
                result = future.result(timeout=20)
                db.upsert_valuation(
                    property_id,
                    source,
                    result.get("estimated_value"),
                    result.get("detail_url"),
                    result.get("raw"),
                )
            except Exception as exc:
                logger.debug("Valuation %s failed for property %d: %s", source, property_id, exc)


def start_background_scrape(max_counties: int = None):
    """Launch scrape in a daemon thread and return immediately."""
    t = threading.Thread(target=run_full_scrape, kwargs={"max_counties": max_counties}, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db.init_db()
    run_full_scrape()
