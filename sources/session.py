"""Shared session factory — uses cloudscraper to bypass WAF/Cloudflare on target sites."""

import ssl
import random
import urllib3
import cloudscraper

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_PLATFORMS = ["windows", "darwin", "linux"]


def make_session():
    """Return a cloudscraper session with SSL verification disabled.

    cloudscraper creates its own ssl.SSLContext (PROTOCOL_TLS_CLIENT) which
    has check_hostname=True by default.  Setting session.verify=False after
    the fact raises "Cannot set verify_mode to CERT_NONE when check_hostname
    is enabled."  Instead we reach into the adapter's pool manager and patch
    the context in-place — check_hostname=False must come first.
    """
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": random.choice(_PLATFORMS),
            "mobile": False,
        }
    )

    # Patch cloudscraper's SSL context to ignore cert errors
    # (realforeclose.com CDN has a hostname mismatch on its certificate).
    try:
        adapter = scraper.get_adapter(url="https://x")
        if hasattr(adapter, "poolmanager"):
            ctx = adapter.poolmanager.connection_pool_kw.get("ssl_context")
            if ctx:
                ctx.check_hostname = False          # must be first
                ctx.verify_mode = ssl.CERT_NONE
            else:
                # Older cloudscraper: rebuild pool manager without SSL verify
                kw = {k: v for k, v in adapter.poolmanager.connection_pool_kw.items()
                      if k != "ssl_context"}
                kw["cert_reqs"] = "CERT_NONE"
                kw["assert_hostname"] = False
                adapter.poolmanager = urllib3.PoolManager(**kw)
    except Exception:
        pass  # best-effort; scraper still usable even if patch fails

    return scraper
