import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
DOCS_DATA_DIR = BASE_DIR / "docs" / "data"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "items").mkdir(parents=True, exist_ok=True)

# CKAN Config
CKAN_SEARCH_URL = "https://catalog.data.metro.tokyo.lg.jp/api/3/action/package_search"
TAITO_ORG_ID = "t131067"

# Geocoding Config
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.yuiseki.net")
GEOCODE_CACHE_PATH = DATA_DIR / "geocoding_cache.json"

# Taito-ku defaults (center of Taito-ku)
TAITO_CENTER_LAT = 35.7138
TAITO_CENTER_LON = 139.7810
TAITO_BBOX = [139.76, 35.69, 139.81, 35.74] # [min_lon, min_lat, max_lon, max_lat]

# Target facility dataset patterns/names in Phase 1
TARGET_DATASET_KEYWORDS = [
    "スポーツ施設",
    "子ども食堂",
    "公立図書館",
    "都市公園",
    "公営住宅",
    "避難所",
    "文化財",
    "宿泊施設",
    "美容所",
    "理容所",
    "クリーニング所",
    "銭湯",
    "公衆トイレ",
    "公衆喫煙所",
    "公衆無線LAN",
    "福祉",
    "医療",
    "子育て",
]
