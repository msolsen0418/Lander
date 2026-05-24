"""Shared session factory with browser-like headers and SSL verification disabled.

If SCRAPERAPI_KEY is set, all HTTPS requests are routed through ScraperAPI's
residential proxy pool, bypassing IP-based blocks (e.g. realforeclose.com
blocks AWS datacenter ranges).  Sign up free at https://www.scraperapi.com
(1,000 req/month free tier).  Add SCRAPERAPI_KEY to Railway env vars.
"""

import os
import random
import urllib3
import requests
from requests.adapters import HTTPAdapter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY", "")

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


class _NoSSLAdapter(HTTPAdapter):
    """Disables SSL certificate verification at the urllib3 pool level."""

    def init_poolmanager(self, connections, maxsize, block=False, **kw):
        self.poolmanager = urllib3.PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            cert_reqs="CERT_NONE",
            assert_hostname=False,
        )


def make_session() -> requests.Session:
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

    if _SCRAPERAPI_KEY:
        # Route through ScraperAPI residential proxies to bypass datacenter IP blocks.
        proxy = f"http://scraperapi:{_SCRAPERAPI_KEY}@proxy-server.scraperapi.com:8001"
        session.proxies.update({"http": proxy, "https": proxy})

    return session
