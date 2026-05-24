"""Shared session factory for listing scrapers.

Three session types:
  make_direct_session()  — No proxy. Use for government/court sites accessible
                           from Railway IPs (realforeclose.com county subdomains,
                           county property appraiser sites).

  make_proxy_session()   — Residential proxy for sites that block datacenter IPs
                           (Zillow, Redfin). Priority order:
                             1. HTTP_PROXY env var  (any SOCKS5/HTTP proxy URL,
                                e.g. SmartProxy: http://user:pass@gate.smartproxy.com:7000)
                             2. SCRAPERAPI_KEY env var
                             3. Falls back to direct (expect 403 from Zillow/Redfin)

  make_session()         — Legacy alias for make_proxy_session(). Kept so existing
                           callers don't break.

Recommended proxy for Railway: SmartProxy residential ~$3.50/GB.
Set HTTP_PROXY=http://user:pass@gate.smartproxy.com:7000 in Railway env vars.
"""

import os
import ssl
import random
import logging
import urllib3
import requests
from requests import PreparedRequest
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY", "")
_HTTP_PROXY = os.getenv("HTTP_PROXY", "") or os.getenv("HTTPS_PROXY", "")

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


class _ScraperAPISession(requests.Session):
    """Session that rewrites every GET through ScraperAPI's URL-based API.

    The request to api.scraperapi.com is plain HTTP — no SSL cert issues.
    ScraperAPI fetches the real target over HTTPS from a residential IP.
    """

    def __init__(self, api_key: str):
        super().__init__()
        self._api_key = api_key

    def get(self, url, **kwargs):
        # Merge any caller params into the target URL before proxying
        params = kwargs.pop("params", None)
        if params:
            p = PreparedRequest()
            p.prepare_url(url, params)
            url = p.url
        # premium=true uses harder-to-detect proxies; country_code forces US IP
        scraperapi_params = {
            "api_key": self._api_key,
            "url": url,
            "country_code": "us",
            "premium": "true",
        }
        kwargs["timeout"] = max(kwargs.get("timeout", 90), 90)
        resp = super().get("http://api.scraperapi.com", params=scraperapi_params, **kwargs)
        if not resp.ok:
            logger.error(
                "ScraperAPI %d for %s — body: %s",
                resp.status_code, url, resp.text[:400],
            )
        return resp


def make_proxy_session() -> requests.Session:
    """Session that routes through a residential proxy for anti-bot sites (Zillow, Redfin).

    Priority:
      1. HTTP_PROXY / HTTPS_PROXY env var — any proxy URL works
         e.g. SmartProxy: http://user:pass@gate.smartproxy.com:7000
      2. SCRAPERAPI_KEY env var
      3. Direct request (will fail for Zillow/Redfin from Railway datacenter IPs)
    """
    profile = random.choice(_PROFILES)

    if _HTTP_PROXY:
        session = requests.Session()
        session.mount("https://", _NoSSLAdapter())
        session.proxies = {"http": _HTTP_PROXY, "https": _HTTP_PROXY}
    elif _SCRAPERAPI_KEY:
        session = _ScraperAPISession(_SCRAPERAPI_KEY)
    else:
        session = requests.Session()
        session.mount("https://", _NoSSLAdapter())

    session.headers.update(
        {
            "User-Agent": profile["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": profile["sec-ch-ua"],
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": profile["sec-ch-ua-platform"],
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
        }
    )
    return session


def make_session() -> requests.Session:
    """Legacy alias for make_proxy_session()."""
    return make_proxy_session()


def make_direct_session() -> requests.Session:
    """Direct requests session — never routes through ScraperAPI.

    Use this for sites that are accessible from Railway IPs without a proxy
    (government/court sites, SSR aggregators, etc.).
    """
    profile = random.choice(_PROFILES)
    session = requests.Session()
    session.mount("https://", _NoSSLAdapter())
    session.headers.update(
        {
            "User-Agent": profile["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": profile["sec-ch-ua"],
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": profile["sec-ch-ua-platform"],
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
        }
    )
    return session
