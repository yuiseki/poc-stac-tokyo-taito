import json
import logging
import re
import asyncio
from typing import Dict, Tuple, Optional
import httpx
from poc_stac_tokyo_taito.config import NOMINATIM_URL, GEOCODE_CACHE_PATH, TAITO_CENTER_LAT, TAITO_CENTER_LON

logger = logging.getLogger(__name__)

class Geocoder:
    def __init__(
        self,
        nominatim_url: str = NOMINATIM_URL,
        cache_path=GEOCODE_CACHE_PATH,
        delay_seconds: float = 0.0
    ):
        self.nominatim_url = nominatim_url.rstrip("/")
        self.cache_path = cache_path
        self.delay_seconds = delay_seconds
        self.cache: Dict[str, Tuple[float, float]] = {}
        self._load_cache()

    def is_within_taito(self, lon: float, lat: float) -> bool:
        """Check if coordinates are within a safe bounding box for Taito-ku."""
        return (139.75 <= lon <= 139.83) and (35.68 <= lat <= 35.75)

    def _load_cache(self):
        """Load the geocoding cache from disk."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Convert list coordinates back to tuples and filter out invalid coordinates
                filtered_cache = {}
                invalid_count = 0
                for k, v in data.items():
                    lon, lat = v[0], v[1]
                    if self.is_within_taito(lon, lat):
                        filtered_cache[k] = (lon, lat)
                    else:
                        logger.warning(f"Removing invalid cache entry: '{k}' -> ({lon}, {lat}) (outside Taito-ku)")
                        invalid_count += 1
                
                self.cache = filtered_cache
                logger.info(f"Loaded {len(self.cache)} valid entries from geocoding cache. Removed {invalid_count} invalid ones.")
                if invalid_count > 0:
                    self._save_cache()
            except Exception as e:
                logger.warning(f"Failed to load geocoding cache: {e}. Starting fresh.")
                self.cache = {}
        else:
            self.cache = {}

    def _save_cache(self):
        """Save the geocoding cache to disk."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
            logger.debug("Saved geocoding cache to disk.")
        except Exception as e:
            logger.error(f"Failed to save geocoding cache: {e}")

    def clean_address(self, address: str) -> str:
        """Clean address text for better search matching."""
        if not address:
            return ""
        # Remove extra whitespace and special characters
        cleaned = re.sub(r'\s+', ' ', address).strip()
        return cleaned

    def get_fallback_address(self, address: str) -> Optional[str]:
        """
        Simplify the address to town/chome level (e.g. remove house numbers)
        Example: "東京都台東区東上野4-5-6" -> "東京都台東区東上野4" or "東京都台東区東上野"
        """
        if not address:
            return None

        # Look for the last chunk of numbers (e.g., 4-5-6 or 4丁目5番6号 or 4丁目5)
        # Try to find common structures and strip house/block numbers
        match_chome = re.search(r'^(東京都台東区[^\s\d]+(?:\d+丁目|\d+)?).*', address)
        if match_chome:
            simplified = match_chome.group(1).strip()
            if simplified != address:
                return simplified
        
        # Fallback to general Taito-ku prefix + town name if found
        match_town = re.search(r'^(東京都台東区[^\s\d]+).*', address)
        if match_town:
            simplified = match_town.group(1).strip()
            if simplified != address:
                return simplified

        return None

    async def geocode(self, address: str) -> Tuple[float, float, bool]:
        """
        Geocode an address. Returns (longitude, latitude, is_fallback_used).
        Uses cache first, then calls Nominatim with 1s delay if needed.
        """
        cleaned = self.clean_address(address)
        if not cleaned:
            return TAITO_CENTER_LON, TAITO_CENTER_LAT, True

        # Check Cache
        if cleaned in self.cache:
            lon, lat = self.cache[cleaned]
            return lon, lat, False

        # Try Geocoding Full Address
        lon, lat = await self._call_nominatim(cleaned)
        if lon is not None and lat is not None:
            self.cache[cleaned] = (lon, lat)
            self._save_cache()
            return lon, lat, False

        # Try Geocoding Simplified/Fallback Address
        fallback_addr = self.get_fallback_address(cleaned)
        if fallback_addr and fallback_addr != cleaned:
            logger.info(f"Full address geocoding failed. Trying fallback address: '{fallback_addr}' for '{cleaned}'")
            # Check cache for fallback first
            if fallback_addr in self.cache:
                lon, lat = self.cache[fallback_addr]
                # Also save the original query mapped to this result to avoid future queries
                self.cache[cleaned] = (lon, lat)
                self._save_cache()
                return lon, lat, True

            lon, lat = await self._call_nominatim(fallback_addr)
            if lon is not None and lat is not None:
                self.cache[fallback_addr] = (lon, lat)
                self.cache[cleaned] = (lon, lat)
                self._save_cache()
                return lon, lat, True

        # Complete fallback: Taito-ku center
        logger.warning(f"Geocoding completely failed for address: '{address}'. Using Taito-ku center.")
        return TAITO_CENTER_LON, TAITO_CENTER_LAT, True

    async def _call_nominatim(self, address: str) -> Tuple[Optional[float], Optional[float]]:
        """Call Nominatim API to geocode a single address."""
        # Enforce rate limit delay
        await asyncio.sleep(self.delay_seconds)
        
        headers = {
            "User-Agent": "poc-stac-tokyo-taito/0.1.0 (yuiseki@gmail.com)"
        }
        params = {
            "q": address,
            "format": "json",
            "limit": 1,
            "viewbox": "139.75,35.75,139.83,35.68",  # left, top, right, bottom (Taito-ku bounding box)
            "bounded": 1
        }
        
        logger.debug(f"Calling Nominatim API: {self.nominatim_url}/search with q='{address}'")
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(f"{self.nominatim_url}/search", params=params, headers=headers)
                response.raise_for_status()
                results = response.json()
                
                if results and len(results) > 0:
                    lon = float(results[0]["lon"])
                    lat = float(results[0]["lat"])
                    if self.is_within_taito(lon, lat):
                        logger.debug(f"Geocoding success: {address} -> ({lon}, {lat})")
                        return lon, lat
                    else:
                        logger.warning(f"Nominatim returned coordinates outside Taito-ku: '{address}' -> ({lon}, {lat})")
                        return None, None
                    
                logger.info(f"Nominatim returned no results for: '{address}'")
                return None, None
            except Exception as e:
                logger.error(f"Error calling Nominatim API for '{address}': {e}")
                return None, None
