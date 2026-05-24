"""
test_scrapers.py — smoke-test all three scraper modules.

Run from the project root:
    python test_scrapers.py

Exit code 0 = all scrapers ran without crashing and returned a list.
Exit code 1 = at least one scraper raised an exception.

This test does NOT assert a minimum listing count because auctions vary by
date — what matters is that each scraper returns a list (possibly empty)
without raising.
"""

import sys
import logging

sys.path.insert(0, "/home/user/Lander")
logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

results = []


def run_test(label, fn):
    print(f"\n{'='*60}")
    print(f"Testing: {label}")
    print("=" * 60)
    try:
        listings = fn()
        assert isinstance(listings, list), f"Expected list, got {type(listings)}"
        print(f"  Returned {len(listings)} listing(s)")
        if listings:
            sample = listings[0]
            print(f"  Sample: {sample}")
        print(f"  {PASS}")
        results.append((label, True, len(listings), None))
    except Exception as exc:
        import traceback
        print(f"  Exception: {exc}")
        traceback.print_exc()
        print(f"  {FAIL}")
        results.append((label, False, 0, str(exc)))


# ── floridapublicnotices ──────────────────────────────────────────────────────
from sources import floridapublicnotices
run_test("floridapublicnotices.scrape()", floridapublicnotices.scrape)

# ── clerkauction ─────────────────────────────────────────────────────────────
from sources import clerkauction
run_test("clerkauction.scrape()", clerkauction.scrape)

# ── realforeclose_pw ─────────────────────────────────────────────────────────
from sources import realforeclose_pw
run_test(
    "realforeclose_pw.scrape(max_counties=2)",
    lambda: realforeclose_pw.scrape(max_counties=2),
)

# ── summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("SUMMARY")
print("=" * 60)
all_passed = True
for label, ok, count, err in results:
    status = PASS if ok else FAIL
    print(f"  {status}  {label}  ({count} listings)")
    if err:
        print(f"         Error: {err}")
    if not ok:
        all_passed = False

print()
if all_passed:
    print("All scrapers passed.")
    sys.exit(0)
else:
    print("One or more scrapers FAILED.")
    sys.exit(1)
