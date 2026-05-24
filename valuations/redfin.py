"""
Redfin estimate lookup via their unofficial (but publicly accessible) API.

Flow:
1. POST to Redfin's location-autocomplete endpoint to find the property.
2. Fetch property details via the /api/home/details/ endpoint.
3. Extract the Redfin Estimate from the JSON response.
"""

import json
import re
import time
import logging
import threading
from urllib.parse import quote
from sources.session import make_proxy_session

logger = logging.getLogger(__name__)

BASE = "https://www.redfin.com"
_local = threading.local()


def _get_session():
    if not hasattr(_local, "session"):
        _local.session = make_proxy_session()
        _local.session.headers.update(
            {
                "Referer": "https://www.redfin.com/",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
    return _local.session


def get_estimate(address: str, city: str = "", state: str = "FL", zip_code: str = "") -> dict:
    """
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
        prop_url, prop_id = _autocomplete_search(full_address)
        if not prop_url:
            return result
        result["detail_url"] = BASE + prop_url if prop_url.startswith("/") else prop_url

        time.sleep(1.0)
        estimate, raw = _fetch_estimate(prop_id or prop_url)
        result["estimated_value"] = estimate
        result["raw"] = raw
    except Exception as exc:
        logger.debug("Redfin lookup failed for '%s': %s", full_address, exc)

    return result


def _build_address(address: str, city: str, state: str, zip_code: str) -> str:
    parts = [address]
    if city:
        parts.append(city)
    parts.append(state)
    if zip_code:
        parts.append(zip_code)
    return ", ".join(p for p in parts if p)


def _autocomplete_search(full_address: str) -> tuple[str | None, str | None]:
    """Return (property_url_path, property_id) from Redfin's autocomplete."""
    session = _get_session()
    encoded = quote(full_address)
    url = f"{BASE}/stingray/do/location-autocomplete?location={encoded}&v=2&al=1&co=false&zh=false&ci=false&nr=1"

    resp = session.get(url, timeout=10)
    resp.raise_for_status()

    # Redfin prepends "{}&&" before JSON for XSS protection
    text = resp.text
    if text.startswith("{}&&"):
        text = text[4:]
    data = json.loads(text)

    items = data.get("payload", {}).get("exactMatch") or {}
    if not items:
        suggestions = data.get("payload", {}).get("sections", [])
        for section in suggestions:
            rows = section.get("rows", [])
            if rows:
                items = rows[0]
                break

    if not items:
        return None, None

    url_path = items.get("url", "")
    # Try to extract property/listing ID from URL
    # Redfin URLs: /FL/Miami/123-Main-St-33101/home/12345678
    prop_id = None
    m = re.search(r"/home/(\d+)", url_path)
    if m:
        prop_id = m.group(1)

    return url_path, prop_id


def _fetch_estimate(prop_id_or_url: str) -> tuple[float | None, dict]:
    """Fetch Redfin estimate for a property ID."""
    session = _get_session()

    # If we have a numeric property ID, use the API
    if prop_id_or_url and prop_id_or_url.isdigit():
        api_url = f"{BASE}/api/home/details/aboveTheFold?propertyId={prop_id_or_url}&accessLevel=1"
        resp = session.get(api_url, timeout=12)
        resp.raise_for_status()

        text = resp.text
        if text.startswith("{}&&"):
            text = text[4:]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None, {}

        estimate = _extract_estimate_from_payload(data.get("payload", {}))
        return estimate, {"property_id": prop_id_or_url}

    # Fallback: scrape the property page
    prop_url = prop_id_or_url if prop_id_or_url.startswith("http") else BASE + prop_id_or_url
    resp = session.get(prop_url, timeout=15)
    resp.raise_for_status()

    # Look for estimate in page JSON
    m = re.search(r'"avm"\s*:\s*\{([^}]+)\}', resp.text)
    if m:
        try:
            avm_str = "{" + m.group(1) + "}"
            avm = json.loads(avm_str)
            value = avm.get("value") or avm.get("amount")
            if value:
                return float(value), {}
        except Exception:
            pass

    # Broader search for estimate value
    m2 = re.search(r'"estimatedValue"\s*:\s*(\d+)', resp.text)
    if m2:
        return float(m2.group(1)), {}

    return None, {}


def _extract_estimate_from_payload(payload: dict) -> float | None:
    """Navigate Redfin payload structure to find AVM estimate."""
    # Various paths Redfin uses for estimates
    for path in [
        ["avmInfo", "predictedValue"],
        ["avmInfo", "value"],
        ["avm", "value"],
        ["avm", "amount"],
        ["estimatedValue"],
        ["propertyHistoryInfo", "avmValue"],
    ]:
        val = payload
        for key in path:
            if isinstance(val, dict) and key in val:
                val = val[key]
            else:
                val = None
                break
        if val and isinstance(val, (int, float)) and val > 1000:
            return float(val)

    # Recursive search as fallback
    return _find_estimate_recursive(payload, depth=0)


def _find_estimate_recursive(obj, depth: int) -> float | None:
    if depth > 6:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ("estimatedvalue", "predictedvalue", "avmvalue") and isinstance(v, (int, float)) and v > 10000:
                return float(v)
            result = _find_estimate_recursive(v, depth + 1)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj[:10]:
            result = _find_estimate_recursive(item, depth + 1)
            if result:
                return result
    return None
