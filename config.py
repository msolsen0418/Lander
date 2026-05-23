import os

# DB_DIR is set to /data when a Railway/Render persistent volume is mounted there.
# Falls back to the current directory for local dev.
_DB_DIR = os.getenv("DB_DIR", ".")
os.makedirs(_DB_DIR, exist_ok=True)
DATABASE_PATH = os.path.join(_DB_DIR, "properties.db")

# How long to cache valuations before re-fetching (seconds)
VALUATION_CACHE_TTL = 6 * 3600  # 6 hours

# Seconds to wait between requests to the same domain
REQUEST_DELAY = 1.5

# Florida county -> county property appraiser config
# "api_type" determines which lookup strategy to use
COUNTY_APPRAISER_CONFIG = {
    "Miami-Dade": {
        "api_type": "miamidade",
        "search_url": "https://www.miamidade.gov/Apps/PA/propertysearch/",
    },
    "Broward": {
        "api_type": "broward",
        "search_url": "https://web.bcpa.net/bcpaclient/",
    },
    "Palm Beach": {
        "api_type": "palmbeach",
        "search_url": "https://www.pbcgov.com/papa/",
    },
    "Hillsborough": {
        "api_type": "hillsborough",
        "search_url": "https://www.hcpafl.org/",
    },
    "Orange": {
        "api_type": "orange",
        "search_url": "https://www.ocpafl.org/",
    },
    "Duval": {
        "api_type": "duval",
        "search_url": "https://paopropertysearch.coj.net/",
    },
    "Pinellas": {
        "api_type": "pinellas",
        "search_url": "https://www.pcpao.gov/",
    },
    "Lee": {
        "api_type": "lee",
        "search_url": "https://www.leepa.org/",
    },
    "Collier": {
        "api_type": "collier",
        "search_url": "https://www.collierappraiser.com/",
    },
    "Polk": {
        "api_type": "polk",
        "search_url": "https://www.polkpa.org/",
    },
}

# RealForeclose county IDs (FL counties on platform)
# These are discovered dynamically from the homepage; this is a fallback map.
REALFORECLOSE_COUNTY_IDS = {
    "Alachua": 1, "Baker": 2, "Bay": 3, "Bradford": 4, "Brevard": 5,
    "Broward": 6, "Calhoun": 7, "Charlotte": 8, "Citrus": 9, "Clay": 10,
    "Collier": 11, "Columbia": 12, "DeSoto": 13, "Dixie": 14, "Duval": 15,
    "Escambia": 16, "Flagler": 17, "Franklin": 18, "Gadsden": 19, "Gilchrist": 20,
    "Glades": 21, "Gulf": 22, "Hamilton": 23, "Hardee": 24, "Hendry": 25,
    "Hernando": 26, "Highlands": 27, "Hillsborough": 28, "Holmes": 29,
    "Indian River": 30, "Jackson": 31, "Jefferson": 32, "Lafayette": 33,
    "Lake": 34, "Lee": 35, "Leon": 36, "Levy": 37, "Liberty": 38,
    "Madison": 39, "Manatee": 40, "Marion": 41, "Martin": 42,
    "Miami-Dade": 43, "Monroe": 44, "Nassau": 45, "Okaloosa": 46,
    "Okeechobee": 47, "Orange": 48, "Osceola": 49, "Palm Beach": 50,
    "Pasco": 51, "Pinellas": 52, "Polk": 53, "Putnam": 54,
    "Santa Rosa": 55, "Sarasota": 56, "Seminole": 57, "St. Johns": 58,
    "St. Lucie": 59, "Sumter": 60, "Suwannee": 61, "Taylor": 62,
    "Union": 63, "Volusia": 64, "Wakulla": 65, "Walton": 66, "Washington": 67,
}
