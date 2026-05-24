"""
Zillow Zestimate lookup via address search.

Strategy:
1. Use Zillow's autocomplete/search API to find the property URL.
2. Fetch the property page and extract Zestimate from the embedded
   __NEXT_DATA__ JSON blob.

Note: Zillow's official Zestimate API was deprecated in 2019. This uses
the public-facing website which may change. Graceful fallback on failure.
"""

import json
import re
import time
import logging
from urllib.parse import quote
from sources.session import make_proxy_session

logger = logging.getLogger(__name__)

_session = None


def _get_session():
    global _session
    if _session is None:
        _session = make_proxy_session(sticky=True)
        # Zillow expects a referer
        _session.headers["Referer"] = "https://www.zillow.com/"
    return _session


def get_zestimate(address: str, city: str = "", state: str = "FL", zip_code: str = "") -> dict:
    """
    Look up Zillow Zestimate for a property.

    Returns:
        {
            "estimated_value": float | None,
            "detail_url": str | None,
            "raw": dict,
        }
    """
    full_address = _build_address(address, city, state, zip_code)
    result = {"estimated_value": None, "detail_url": None, "raw": {}}

    try:
        property_url = _search_property_url(full_address)
        if not property_url:
            return result
        result["detail_url"] = property_url

        time.sleep(1.0)
        zestimate, raw = _fetch_zestimate_from_page(property_url)
        result["estimated_value"] = zestimate
        result["raw"] = raw
    except Exception as exc:
        logger.debug("Zillow lookup failed for '%s': %s", full_address, exc)

    return result


def _build_address(address: str, city: str, state: str, zip_code: str) -> str:
    parts = [address]
    if city:
        parts.append(city)
    parts.append(state)
    if zip_code:
        parts.append(zip_code)
    return ", ".join(p for p in parts if p)


def _search_property_url(full_address: str) -> str | None:
    """Use Zillow's search suggestions to find the canonical property URL."""
    session = _get_session()
    encoded = quote(full_address)
    url = f"https://www.zillow.com/search/GetSearchPageState.htm?searchQueryState={{%22pagination%22:{{}},%22isMapVisible%22:false,%22mapBounds%22:{{}},%22usersSearchTerm%22:{json.dumps(full_address)},%22filterState%22:{{%22sort%22:{{%22value%22:%22globalrelevanceex%22}},%22ah%22:{{%22value%22:true}}}},%22isListVisible%22:true}}&wants={{%22cat1%22:[%22listResults%22],%22cat2%22:[%22total%22]}}&requestId=1"

    # Simpler: use the autocomplete endpoint
    suggest_url = f"https://www.zillowstatic.com/autocomplete/v3/suggestions?q={encoded}&abKey=&currentUrl=https%3A%2F%2Fwww.zillow.com%2F"

    try:
        resp = session.get(suggest_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        # First result should be closest match
        first = results[0]
        # Build Zillow URL from the metaData
        meta = first.get("metaData", {})
        zillow_url = meta.get("zhid") or first.get("url")
        if zillow_url and zillow_url.startswith("/"):
            return "https://www.zillow.com" + zillow_url
        if zillow_url and zillow_url.startswith("http"):
            return zillow_url

        # Try the display field to build a slug
        display = first.get("display", "")
        if display:
            slug = re.sub(r"[^a-zA-Z0-9]+", "-", display).strip("-").lower()
            return f"https://www.zillow.com/homes/{slug}_rb/"
    except Exception as exc:
        logger.debug("Zillow autocomplete error: %s", exc)

    return None


def _fetch_zestimate_from_page(property_url: str) -> tuple[float | None, dict]:
    """Fetch property page and extract Zestimate from __NEXT_DATA__ JSON."""
    session = _get_session()
    resp = session.get(property_url, timeout=15)
    resp.raise_for_status()

    # Find __NEXT_DATA__ JSON blob
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text, re.DOTALL)
    if not m:
        # Fallback: look for zestimate in any JSON blob
        m2 = re.search(r'"zestimate"\s*:\s*(\d+)', resp.text)
        if m2:
            return float(m2.group(1)), {}
        return None, {}

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None, {}

    # Navigate the Next.js data structure to find zestimate
    zestimate = _dig(data, [
        # Common paths in Zillow's Next.js structure
        "props.pageProps.componentProps.gdpClientCache",
        "props.pageProps.initialReduxState.gdp.propertyPage",
        "props.pageProps.initialData",
    ])

    # If gdpClientCache is a JSON string, parse it
    if isinstance(zestimate, str):
        try:
            zestimate = json.loads(zestimate)
        except Exception:
            pass

    # Try to extract the zestimate value from nested structures
    value = _find_zestimate_value(zestimate if isinstance(zestimate, dict) else data)
    return value, {"source_url": property_url}


def _dig(obj: dict, paths: list[str]):
    """Try multiple dot-separated paths and return the first hit."""
    for path in paths:
        result = obj
        for key in path.split("."):
            if isinstance(result, dict) and key in result:
                result = result[key]
            else:
                result = None
                break
        if result is not None:
            return result
    return None


def _find_zestimate_value(obj, depth: int = 0) -> float | None:
    """Recursively search for 'zestimate' key in a nested dict/list."""
    if depth > 8:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == "zestimate" and isinstance(v, (int, float)) and v > 0:
                return float(v)
            if k.lower() == "zestimate" and isinstance(v, dict):
                amount = v.get("amount") or v.get("value") or v.get("low")
                if amount:
                    return float(amount)
            result = _find_zestimate_value(v, depth + 1)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj[:20]:
            result = _find_zestimate_value(item, depth + 1)
            if result:
                return result
    return None
