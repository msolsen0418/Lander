"""
County Property Appraiser assessed value lookups for Florida counties.

Each major county has its own API or searchable website. This module
implements strategies for the 10 largest counties and provides a
generic fallback for the rest.
"""

import json
import re
import time
import logging
from urllib.parse import quote, urlencode
from sources.session import make_session
from config import COUNTY_APPRAISER_CONFIG

logger = logging.getLogger(__name__)

_session = None


def _get_session():
    global _session
    if _session is None:
        _session = make_session()
    return _session


def get_assessed_value(address: str, city: str, county: str, zip_code: str = "") -> dict:
    """
    Look up county-assessed property value.

    Returns:
        {
            "estimated_value": float | None,
            "detail_url": str | None,
            "raw": dict,
        }
    """
    config = COUNTY_APPRAISER_CONFIG.get(county)
    result = {"estimated_value": None, "detail_url": None, "raw": {}}

    try:
        if config:
            api_type = config["api_type"]
            fn = _STRATEGY_MAP.get(api_type)
            if fn:
                return fn(address, city, zip_code, config)
        # Generic fallback
        return _generic_lookup(address, city, county, zip_code)
    except Exception as exc:
        logger.debug("County appraiser lookup failed (%s): %s", county, exc)

    return result


# ── County-specific strategies ───────────────────────────────────────────────

def _miamidade(address: str, city: str, zip_code: str, config: dict) -> dict:
    """Miami-Dade Property Appraiser — uses their public JSON API."""
    session = _get_session()
    encoded = quote(address)
    api_url = f"https://www.miamidade.gov/Apps/PA/propertysearch/api/search?qry={encoded}&folioNumber=&type=address"
    resp = session.get(api_url, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("MinimumPropertyInfos", data.get("PropertyInfos", []))
    if not results:
        return {"estimated_value": None, "detail_url": None, "raw": {}}

    prop = results[0]
    folio = prop.get("FolioNumber", prop.get("Strap", ""))
    value = float(prop.get("AssessedValue", 0) or 0) or float(prop.get("JustValue", 0) or 0)
    detail_url = f"https://www.miamidade.gov/Apps/PA/propertysearch/#/?folio={folio}"
    return {"estimated_value": value if value > 0 else None, "detail_url": detail_url, "raw": prop}


def _broward(address: str, city: str, zip_code: str, config: dict) -> dict:
    """Broward County Property Appraiser — public API."""
    session = _get_session()
    encoded = quote(address.upper())
    api_url = f"https://web.bcpa.net/bcpaclient/api/Property/SearchByAddress?address={encoded}&pageSize=5"
    resp = session.get(api_url, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    items = data if isinstance(data, list) else data.get("results", data.get("Properties", []))
    if not items:
        return {"estimated_value": None, "detail_url": None, "raw": {}}

    prop = items[0]
    assessed = float(prop.get("AssessedValue", 0) or prop.get("TotalJustValue", 0) or 0)
    folio = prop.get("Folio", prop.get("ParcelID", ""))
    detail_url = f"https://web.bcpa.net/bcpaclient/#/Record-Search?folio={folio}"
    return {"estimated_value": assessed if assessed > 0 else None, "detail_url": detail_url, "raw": prop}


def _palmbeach(address: str, city: str, zip_code: str, config: dict) -> dict:
    """Palm Beach County — public property search API."""
    session = _get_session()
    params = urlencode({"PropertyAddress": address, "Municipality": city, "ZipCode": zip_code, "maxResults": 5})
    api_url = f"https://www.pbcgov.com/papa/Asps/PropertyDetail/PropertyDetail.aspx/GetPropertyByAddress?{params}"
    resp = session.get(api_url, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    props = data.get("d", data) if isinstance(data, dict) else data
    if isinstance(props, str):
        try:
            props = json.loads(props)
        except Exception:
            props = []
    if not props:
        return {"estimated_value": None, "detail_url": None, "raw": {}}

    prop = props[0] if isinstance(props, list) else props
    value = float(prop.get("TotalAssessed", 0) or prop.get("JustValue", 0) or 0)
    parcel = prop.get("ParcelID", prop.get("PCN", ""))
    detail_url = f"https://www.pbcgov.com/papa/Asps/PropertyDetail/PropertyDetail.aspx?parcel={parcel}"
    return {"estimated_value": value if value > 0 else None, "detail_url": detail_url, "raw": prop}


def _hillsborough(address: str, city: str, zip_code: str, config: dict) -> dict:
    """Hillsborough County — public property search."""
    session = _get_session()
    encoded = quote(address)
    api_url = f"https://www.hcpafl.org/api/PropertySearch/SearchAddress?address={encoded}&count=5"
    resp = session.get(api_url, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        return {"estimated_value": None, "detail_url": None, "raw": {}}

    prop = items[0]
    value = float(prop.get("AssessedValue", 0) or prop.get("TotalMarketValue", 0) or 0)
    parcel = prop.get("ParcelID", prop.get("Folio", ""))
    detail_url = f"https://www.hcpafl.org/PropertyDetail/{parcel}"
    return {"estimated_value": value if value > 0 else None, "detail_url": detail_url, "raw": prop}


def _orange(address: str, city: str, zip_code: str, config: dict) -> dict:
    """Orange County — public GIS property search."""
    session = _get_session()
    encoded = quote(address)
    api_url = f"https://www.ocpafl.org/api/parcels/search?address={encoded}&limit=5"
    resp = session.get(api_url, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("parcels", data if isinstance(data, list) else [])
    if not items:
        return {"estimated_value": None, "detail_url": None, "raw": {}}

    prop = items[0]
    value = float(prop.get("assessedValue", 0) or prop.get("justValue", 0) or 0)
    parcel = prop.get("parcelId", prop.get("pin", ""))
    detail_url = f"https://www.ocpafl.org/searches/parceldetail.aspx?parcel={parcel}"
    return {"estimated_value": value if value > 0 else None, "detail_url": detail_url, "raw": prop}


def _duval(address: str, city: str, zip_code: str, config: dict) -> dict:
    """Duval County — public property appraiser search."""
    session = _get_session()
    encoded = quote(address)
    api_url = f"https://paopropertysearch.coj.net/Basic/api/search?address={encoded}&count=5"
    resp = session.get(api_url, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    items = data if isinstance(data, list) else data.get("properties", data.get("results", []))
    if not items:
        return {"estimated_value": None, "detail_url": None, "raw": {}}

    prop = items[0]
    value = float(prop.get("assessedValue", 0) or prop.get("totalValue", 0) or 0)
    parcel = prop.get("parcelId", prop.get("re", ""))
    detail_url = f"https://paopropertysearch.coj.net/Basic/Detail.aspx?RE={parcel}"
    return {"estimated_value": value if value > 0 else None, "detail_url": detail_url, "raw": prop}


def _pinellas(address: str, city: str, zip_code: str, config: dict) -> dict:
    """Pinellas County — public property appraiser."""
    session = _get_session()
    encoded = quote(address)
    api_url = f"https://www.pcpao.gov/api/property/search?address={encoded}&limit=5"
    resp = session.get(api_url, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        return {"estimated_value": None, "detail_url": None, "raw": {}}

    prop = items[0]
    value = float(prop.get("assessedValue", 0) or prop.get("justValue", 0) or 0)
    parcel = prop.get("parcelNumber", prop.get("parcelId", ""))
    detail_url = f"https://www.pcpao.gov/PropertyDetail?parcel={parcel}"
    return {"estimated_value": value if value > 0 else None, "detail_url": detail_url, "raw": prop}


def _lee(address: str, city: str, zip_code: str, config: dict) -> dict:
    """Lee County — public property appraiser."""
    session = _get_session()
    encoded = quote(address)
    api_url = f"https://www.leepa.org/api/property/search?address={encoded}&maxRecords=5"
    resp = session.get(api_url, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    items = data if isinstance(data, list) else data.get("properties", [])
    if not items:
        return {"estimated_value": None, "detail_url": None, "raw": {}}

    prop = items[0]
    value = float(prop.get("assessedValue", 0) or prop.get("justValue", 0) or 0)
    strap = prop.get("strapNumber", prop.get("strap", ""))
    detail_url = f"https://www.leepa.org/Display/DisplayParcel.aspx?STRAP={strap}"
    return {"estimated_value": value if value > 0 else None, "detail_url": detail_url, "raw": prop}


def _collier(address: str, city: str, zip_code: str, config: dict) -> dict:
    """Collier County — public property appraiser."""
    session = _get_session()
    encoded = quote(address)
    api_url = f"https://www.collierappraiser.com/api/search?address={encoded}&limit=5"
    resp = session.get(api_url, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        return {"estimated_value": None, "detail_url": None, "raw": {}}

    prop = items[0]
    value = float(prop.get("assessedValue", 0) or prop.get("totalValue", 0) or 0)
    parcel = prop.get("parcelId", prop.get("folio", ""))
    detail_url = f"https://www.collierappraiser.com/main_search/recorddetail.asp?parcel_id={parcel}"
    return {"estimated_value": value if value > 0 else None, "detail_url": detail_url, "raw": prop}


def _polk(address: str, city: str, zip_code: str, config: dict) -> dict:
    """Polk County — public property appraiser."""
    session = _get_session()
    encoded = quote(address)
    api_url = f"https://www.polkpa.org/ArcIMS/website/polk/propertySearchJSON.php?address={encoded}"
    resp = session.get(api_url, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    items = data if isinstance(data, list) else data.get("features", data.get("results", []))
    if not items:
        return {"estimated_value": None, "detail_url": None, "raw": {}}

    prop = items[0]
    attrs = prop.get("attributes", prop) if isinstance(prop, dict) else {}
    value = float(attrs.get("ASSESSED_VALUE", 0) or attrs.get("JUST_VALUE", 0) or 0)
    parcel = attrs.get("PARCEL_ID", attrs.get("ALTKEY", ""))
    detail_url = f"https://www.polkpa.org/CamaDisplay.aspx?OutputMode=Display&SearchType=RealEstate&Strap={parcel}"
    return {"estimated_value": value if value > 0 else None, "detail_url": detail_url, "raw": attrs}


def _generic_lookup(address: str, city: str, county: str, zip_code: str) -> dict:
    """
    Generic fallback: search the Florida Department of Revenue GIS
    or a common county property search pattern.
    """
    session = _get_session()
    # Many smaller FL counties use the same Aptitude/GovOS platform
    # Try a few common URL patterns
    county_slug = county.lower().replace(" ", "").replace("-", "").replace(".", "")
    urls_to_try = [
        f"https://qpublic.schneidercorp.com/Application.aspx?app=Florida{county_slug.title()}CountyFL&PageType=SearchResults&Address={quote(address)}",
    ]

    for url in urls_to_try:
        try:
            resp = session.get(url, timeout=10)
            if resp.ok:
                # Look for assessed value in the page
                m = re.search(r'[Aa]ssessed\s*[Vv]alue[^$]*\$\s*([\d,]+)', resp.text)
                if m:
                    value = float(m.group(1).replace(",", ""))
                    return {"estimated_value": value, "detail_url": url, "raw": {}}
        except Exception:
            pass

    return {"estimated_value": None, "detail_url": None, "raw": {}}


_STRATEGY_MAP = {
    "miamidade": _miamidade,
    "broward": _broward,
    "palmbeach": _palmbeach,
    "hillsborough": _hillsborough,
    "orange": _orange,
    "duval": _duval,
    "pinellas": _pinellas,
    "lee": _lee,
    "collier": _collier,
    "polk": _polk,
}
