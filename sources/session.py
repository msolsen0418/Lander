"""Shared session factory for listing scrapers.

If SCRAPERAPI_KEY is set, GET requests are routed through ScraperAPI's
URL-based API (http://api.scraperapi.com?api_key=KEY&url=TARGET).
This is an HTTP request (no SSL on our side), so there are no SSL cert
issues regardless of the target site.  ScraperAPI also rotates residential
IPs, bypassing datacenter IP blocks on sites like realforeclose.com.

Sign up free at https://www.scraperapi.com (1,000 req/month free tier).
Add SCRAPERAPI_KEY as a Railway environment variable.
"""

import os
import ssl
import random
import urllib3
import requests
from urllib.parse import quote
from requests import PreparedRequest
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
        # Merge any params kwarg into the URL string first
        params = kwargs.pop("params", None)
        if params:
            p = PreparedRequest()
            p.prepare_url(url, params)
            url = p.url
        # Rewrite through ScraperAPI
        url = f"http://api.scraperapi.com?api_key={self._api_key}&url={quote(url, safe='')}"
        return super().get(url, **kwargs)


def make_session() -> requests.Session:
    profile = random.choice(_PROFILES)

    if _SCRAPERAPI_KEY:
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
