"""
County Property Appraiser assessed value lookups for Florida counties.

Two modes:
  - ATTOM_API_KEY env var set → uses Attom Data Solutions API (free 100 req/month
    trial at attomdata.com). Returns both assessed value and AVM estimate.
  - HTTP_PROXY env var set → routes requests through a residential proxy so that
    county GIS/appraiser sites are reachable from Railway's datacenter IPs.
  - Neither set → returns empty results (county sites block Railway IPs directly).
"""

import os
import re
import logging
from urllib.parse import quote, urlencode
from sources.session import make_direct_session, make_proxy_session

logger = logging.getLogger(__name__)

_ATTOM_KEY = os.getenv("ATTOM_API_KEY", "")

# ArcGIS Feature/Map Service parcel endpoints for FL counties.
# These work when routed through a residential proxy (HTTP_PROXY env var).
_ARCGIS = {
    "Alachua":      ("https://maps.alachuacounty.us/gisdata/rest/services/Webservices/PropertySearch/MapServer/0", "SITEADDRESS"),
    "Broward":      ("https://gisdata.broward.org/arcgis/rest/services/Parcels/FeatureServer/0", "SITE_ADDR"),
    "Charlotte":    ("https://www.ccgis.org/server/rest/services/Property/Parcels/FeatureServer/0", "SITEADDRESS"),
    "Citrus":       ("https://gis.citruspa.org/arcgis/rest/services/Parcels/Parcels/MapServer/0", "SITE_ADDR"),
    "Clay":         ("https://gis.claycountygov.com/arcgis/rest/services/ParcelSearch/MapServer/0", "SITE_ADDRESS"),
    "Duval":        ("https://e.coj.net/arcgis/rest/services/PAO/PAOParcelSearch/MapServer/0", "SITE_ADDR"),
    "Flagler":      ("https://maps.flaglercounty.gov/arcgis/rest/services/Parcel/Parcel/FeatureServer/0", "SITE_ADDR"),
    "Hillsborough": ("https://gis.hillsboroughcounty.org/arcgis/rest/services/Parcel/Parcels/MapServer/0", "SITEADDRESS"),
    "Indian River": ("https://gis.ircgov.com/arcgis/rest/services/Parcels/Parcels/MapServer/0", "SITEADDRESS"),
    "Lee":          ("https://leepa.org/arcgis/rest/services/ParcelSearch/MapServer/0", "SITE_ADDR"),
    "Leon":         ("https://maps.leonpa.org/arcgis/rest/services/Parcels/Parcels/FeatureServer/0", "SITE_ADDR"),
    "Manatee":      ("https://gis.manateecountyfl.gov/arcgis/rest/services/Parcels/FeatureServer/0", "SITE_ADDR"),
    "Marion":       ("https://gis.marioncountyfl.org/arcgis/rest/services/Parcels/Parcels/MapServer/0", "SITEADDRESS"),
    "Martin":       ("https://maps.martin.fl.us/arcgis/rest/services/Property/Parcels/MapServer/0", "SITEADDRESS"),
    "Miami-Dade":   ("https://services1.arcgis.com/LVRL6VR0u9QHEFjV/arcgis/rest/services/MIAMIDADE_Parcels/FeatureServer/0", "SITE_ADDR"),
    "Orange":       ("https://gis.ocpafl.org/arcgis/rest/services/Parcels/Parcels/FeatureServer/0", "SITEADDRESS"),
    "Palm Beach":   ("https://services.arcgis.com/mStSlIE5FrkXI38M/arcgis/rest/services/PBC_Parcels/FeatureServer/0", "SITE_ADDR"),
    "Pasco":        ("https://gis.pascopa.com/arcgis/rest/services/Parcels/Parcels/FeatureServer/0", "SITE_ADDR"),
    "Pinellas":     ("https://gis.pcpao.gov/arcgis/rest/services/Parcels/Parcels/MapServer/0", "SITEADDRESS"),
    "Polk":         ("https://gis.polkpa.org/arcgis/rest/services/Parcels/Parcels/MapServer/0", "SITE_ADDR"),
    "Sarasota":     ("https://services1.arcgis.com/mStSlIE5FrkXI38M/arcgis/rest/services/Parcels/FeatureServer/0", "SITEADDRESS"),
    "St. Lucie":    ("https://gis.stlucieco.gov/arcgis/rest/services/Parcels/Parcels/MapServer/0", "SITEADDRESS"),
    "Volusia":      ("https://gis.volusia.org/arcgis/rest/services/Parcels/Parcels/FeatureServer/0", "SITE_ADDR"),
}

_VALUE_FIELDS = [
    "ASSESSED_VALUE", "ASSVALUE", "JUST_VALUE", "JUSTVALUE", "TOTALVALUE",
    "TOTAL_ASSESSED_VALUE", "ASSESSED", "AV", "JV", "MKTVAL",
    "assessed_value", "just_value", "total_value", "assessedValue", "justValue",
]


def get_assessed_value(address: str, city: str, county: str, zip_code: str = "") -> dict:
    """Look up assessed value from county property appraiser."""
    result = {"estimated_value": None, "detail_url": None, "raw": {}}

    try:
        if _ATTOM_KEY:
            return _attom_lookup(address, city, county, zip_code)
        if county in _ARCGIS:
            # ArcGIS parcel APIs are public government data; no proxy needed.
            return _arcgis_lookup(county, address)
        logger.debug("County appraiser skipped for %s — county '%s' not in ArcGIS map; set ATTOM_API_KEY for full coverage", address, county)
    except Exception as exc:
        logger.debug("County appraiser lookup failed (%s %s): %s", county, address, exc)

    return result


def _attom_lookup(address: str, city: str, county: str, zip_code: str) -> dict:
    """Use Attom Data Solutions API (ATTOM_API_KEY env var)."""
    import requests as _req
    addr1 = address.strip()
    addr2 = f"{city}, FL {zip_code}".strip(", ")
    url = f"https://api.attomdata.com/propertyapi/v1.0.0/property/address?address1={quote(addr1)}&address2={quote(addr2)}"
    headers = {
        "Accept": "application/json",
        "apikey": _ATTOM_KEY,
    }
    resp = _req.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    props = data.get("property", [])
    if not props:
        return {"estimated_value": None, "detail_url": None, "raw": {}}

    prop = props[0]
    # assessed value from assessment object
    assessed = (
        prop.get("assessment", {}).get("assessed", {}).get("assdttlvalue") or
        prop.get("assessment", {}).get("market", {}).get("mktttlvalue") or
        prop.get("avm", {}).get("amount", {}).get("value")
    )
    value = float(assessed) if assessed else None
    attom_id = prop.get("identifier", {}).get("attomId", "")
    detail_url = f"https://www.attomdata.com/property/{attom_id}" if attom_id else None
    return {"estimated_value": value, "detail_url": detail_url, "raw": prop}


def _arcgis_lookup(county: str, address: str) -> dict:
    """Query county ArcGIS parcel service. Tries direct first; falls back to proxy."""
    base, addr_field = _ARCGIS[county]
    addr_upper = address.upper().strip()
    where = f"UPPER({addr_field}) LIKE '{addr_upper}%'"
    params = urlencode({"where": where, "outFields": "*", "returnGeometry": "false",
                        "resultRecordCount": 3, "f": "json"})
    query_url = f"{base}/query?{params}"

    for session in (make_direct_session(), make_proxy_session()):
        try:
            resp = session.get(query_url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if not features:
                return {"estimated_value": None, "detail_url": None, "raw": {}}
            attrs = features[0].get("attributes", {})
            value = _extract_value(attrs)
            return {"estimated_value": value, "detail_url": base if value else None, "raw": attrs}
        except Exception as exc:
            logger.debug("ArcGIS direct attempt failed for %s: %s", county, exc)

    return {"estimated_value": None, "detail_url": None, "raw": {}}


def _extract_value(attrs: dict) -> float | None:
    for field in _VALUE_FIELDS:
        v = attrs.get(field)
        if v and isinstance(v, (int, float)) and v > 1000:
            return float(v)
        if v and isinstance(v, str):
            cleaned = re.sub(r"[^\d.]", "", v)
            try:
                fv = float(cleaned)
                if fv > 1000:
                    return fv
            except ValueError:
                pass
    return None
