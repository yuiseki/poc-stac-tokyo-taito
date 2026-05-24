import json
import logging
from typing import List, Dict, Any, Tuple
from poc_stac_tokyo_taito.config import DOCS_DATA_DIR
from poc_stac_tokyo_taito.csv_parser import CSVParser
from poc_stac_tokyo_taito.geocoder import Geocoder

logger = logging.getLogger(__name__)

class GeoJSONConverter:
    def __init__(self, geocoder: Geocoder):
        self.geocoder = geocoder
        self.csv_parser = CSVParser()

    async def records_to_geojson(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Convert list of CSV records to a GeoJSON FeatureCollection.
        Geocodes records if coordinates are missing.
        """
        features = []
        
        for idx, record in enumerate(records):
            addr, lon, lat = self.csv_parser.extract_address_and_coordinates(record)
            
            is_fallback = False
            # If coordinates are missing, we geocode using the geocoder
            if lon is None or lat is None:
                if addr:
                    lon, lat, is_fallback = await self.geocoder.geocode(addr)
                else:
                    # No address at all, use default Taito center
                    from poc_stac_tokyo_taito.config import TAITO_CENTER_LAT, TAITO_CENTER_LON
                    lon = TAITO_CENTER_LON
                    lat = TAITO_CENTER_LAT
                    is_fallback = True

            # Prepare properties
            properties = record.copy()
            properties["_resolved_address"] = addr or ""
            properties["_geocoded_fallback"] = is_fallback
            
            feature = {
                "type": "Feature",
                "id": str(idx + 1),
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat]
                },
                "properties": properties
            }
            features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }
        
        return geojson

    def save_geojson(self, dataset_name: str, geojson: Dict[str, Any]) -> str:
        """
        Save the GeoJSON FeatureCollection to docs/data/<dataset_name>.geojson.
        """
        DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
        file_path = DOCS_DATA_DIR / f"{dataset_name}.geojson"
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(geojson, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved GeoJSON to {file_path}")
            return str(file_path)
        except Exception as e:
            logger.error(f"Failed to save GeoJSON to {file_path}: {e}")
            raise
