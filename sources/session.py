"""
Shared HTTP session factory.

Session types
─────────────
make_direct_session()
    No proxy. For government/court sites reachable from Railway IPs
    (realforeclose.com county subdomains, county appraiser GIS APIs).

make_proxy_session(sticky=False)
    Residential proxy for sites that block datacenter IPs (Zillow, Redfin,
    county GIS portals).

    Credential priority:
      1. SMARTPROXY_USER + SMARTPROXY_PASS  →  SmartProxy residential
         gate.smartproxy.com:7000 (HTTP, handles HTTPS via CONNECT tunnel)
         sticky=True appends a random session ID so multi-step lookups
         (Zillow search → property page) use the same exit IP.
      2. HTTP_PROXY / HTTPS_PROXY env var   →  any proxy URL
      3. SCRAPERAPI_KEY env var             →  ScraperAPI premium
      4. Direct (expect 403 from Zillow/Redfin from Railway datacenter IPs)

make_session()
    Legacy alias for make_proxy_session().

Railway setup for SmartProxy
─────────────────────────────
In Railway → Settings → Variables add:
    SMARTPROXY_USER = spxxxxxxx           (your SmartProxy username)
    SMARTPROXY_PASS = <password>

That's it. Sign up at smartproxy.com — residential starts at ~$3.50/GB.
"""

import os
import re
import ssl
import uuid
import random
import logging
import urllib3
import requests
from requests import PreparedRequest
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Credential resolution (read once at import time) ──────────────────────────
_SMARTPROXY_USER = os.getenv("SMARTPROXY_USER", "")
_SMARTPROXY_PASS = os.getenv("SMARTPROXY_PASS", "")
_SMARTPROXY_HOST = "gate.smartproxy.com"
_SMARTPROXY_PORT = 7000          # HTTP proxy; handles HTTPS via CONNECT tunnel
_SMARTPROXY_PORT_STICKY = 7002   # sticky endpoint (same IP per session ID)

_SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY", "")
_HTTP_PROXY = os.getenv("HTTP_PROXY", "") or os.getenv("HTTPS_PROXY", "")

_HAS_SMARTPROXY = bool(_SMARTPROXY_USER and _SMARTPROXY_PASS)
_HAS_PROXY = _HAS_SMARTPROXY or bool(_HTTP_PROXY) or bool(_SCRAPERAPI_KEY)

if _HAS_SMARTPROXY:
    logger.info("SmartProxy residential proxy configured (user=%s)", _SMARTPROXY_USER)
elif _HTTP_PROXY:
    logger.info("Generic HTTP proxy configured")
elif _SCRAPERAPI_KEY:
    logger.info("ScraperAPI proxy configured")
else:
    logger.info(
        "No residential proxy configured — Zillow/Redfin/county GIS will fail. "
        "Set SMARTPROXY_USER + SMARTPROXY_PASS in Railway env vars."
    )

_PROFILES = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-platform": '"Windows"',
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-platform": '"macOS"',
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
        "sec-ch-ua-platform": '"Windows"',
    },
]

_BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "sec-ch-ua-mobile": "?0",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
}


# ── SSL / adapter helpers ──────────────────────────────────────────────────────

def _no_verify_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class _NoSSLAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **kw):
        self.poolmanager = urllib3.PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=_no_verify_ctx(),
        )


# ── ScraperAPI session (legacy) ────────────────────────────────────────────────

class _ScraperAPISession(requests.Session):
    def __init__(self, api_key: str):
        super().__init__()
        self._api_key = api_key

    def get(self, url, **kwargs):
        params = kwargs.pop("params", None)
        if params:
            p = PreparedRequest()
            p.prepare_url(url, params)
            url = p.url
        sp = {"api_key": self._api_key, "url": url, "country_code": "us", "premium": "true"}
        kwargs["timeout"] = max(kwargs.get("timeout", 90), 90)
        resp = super().get("http://api.scraperapi.com", params=sp, **kwargs)
        if not resp.ok:
            logger.error("ScraperAPI %d for %s — %s", resp.status_code, url, resp.text[:300])
        return resp


# ── Public session factories ───────────────────────────────────────────────────

def make_proxy_session(sticky: bool = False) -> requests.Session:
    """
    Residential proxy session for anti-bot sites.

    sticky=True  →  all requests from this session share one exit IP
                    (required for Zillow's multi-step search → page flow).
    sticky=False →  each request may use a different IP (better for Redfin).
    """
    profile = random.choice(_PROFILES)
    session = _build_proxy_session(sticky)
    session.headers.update({**_BROWSER_HEADERS,
                             "User-Agent": profile["User-Agent"],
                             "sec-ch-ua": profile["sec-ch-ua"],
                             "sec-ch-ua-platform": profile["sec-ch-ua-platform"]})
    return session


def _build_proxy_session(sticky: bool) -> requests.Session:
    if _HAS_SMARTPROXY:
        return _smartproxy_session(sticky)
    if _HTTP_PROXY:
        s = requests.Session()
        s.mount("https://", _NoSSLAdapter())
        s.proxies = {"http": _HTTP_PROXY, "https": _HTTP_PROXY}
        return s
    if _SCRAPERAPI_KEY:
        return _ScraperAPISession(_SCRAPERAPI_KEY)
    # No proxy configured — direct (will 403 on Zillow/Redfin)
    s = requests.Session()
    s.mount("https://", _NoSSLAdapter())
    return s


def _smartproxy_session(sticky: bool) -> requests.Session:
    """Build a requests.Session routed through SmartProxy residential."""
    if sticky:
        # Sticky endpoint keeps same exit IP for ~10 min per session ID.
        session_id = uuid.uuid4().hex[:12]
        username = f"{_SMARTPROXY_USER}-sessionid-{session_id}"
        proxy_url = f"http://{username}:{_SMARTPROXY_PASS}@{_SMARTPROXY_HOST}:{_SMARTPROXY_PORT_STICKY}"
    else:
        proxy_url = f"http://{_SMARTPROXY_USER}:{_SMARTPROXY_PASS}@{_SMARTPROXY_HOST}:{_SMARTPROXY_PORT}"

    s = requests.Session()
    s.proxies = {"http": proxy_url, "https": proxy_url}
    # SmartProxy uses a valid TLS cert on their gateway so we can verify normally.
    # But many target sites have cert issues, so keep _NoSSLAdapter for targets.
    s.mount("https://", _NoSSLAdapter())
    return s


def make_session() -> requests.Session:
    """Legacy alias — kept so existing callers don't break."""
    return make_proxy_session(sticky=False)


def make_direct_session() -> requests.Session:
    """Direct session, no proxy. For county auction sites and government portals."""
    profile = random.choice(_PROFILES)
    s = requests.Session()
    s.mount("https://", _NoSSLAdapter())
    s.headers.update({**_BROWSER_HEADERS,
                      "User-Agent": profile["User-Agent"],
                      "sec-ch-ua": profile["sec-ch-ua"],
                      "sec-ch-ua-platform": profile["sec-ch-ua-platform"]})
    return s


def has_residential_proxy() -> bool:
    """Return True only when a real residential proxy is configured.

    ScraperAPI is excluded — it returns 500 for Zillow/Redfin ("protected
    domains") and 429 under concurrent load, causing container crash-loops.
    """
    return _HAS_SMARTPROXY or bool(_HTTP_PROXY)
