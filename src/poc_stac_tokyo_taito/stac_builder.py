import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from poc_stac_tokyo_taito.config import DATA_DIR, TAITO_BBOX, TAITO_CENTER_LAT, TAITO_CENTER_LON

logger = logging.getLogger(__name__)

STAC_COLLECTIONS_INFO = {
    "kurashi-sumai": {
        "title": "くらし・住まい",
        "description": "台東区のくらし・住まいに関する公共施設、公営住宅、その他生活関連データ。"
    },
    "kodomo-kyoiku": {
        "title": "子供・若者・教育",
        "description": "台東区の子ども食堂、教育施設、保育関連施設などのデータ。"
    },
    "kenko-iryo": {
        "title": "健康・医療",
        "description": "台東区の食品衛生施設、美容所・理容所台帳、クリーニング所台帳、銭湯などの保健衛生・医療関連データ。"
    },
    "bunka-geijutsu": {
        "title": "文化・芸術",
        "description": "台東区の文化財、公立図書館、博物館などの歴史・文化関連データ。"
    },
    "kanko": {
        "title": "観光",
        "description": "台東区の宿泊施設（旅館台帳）、観光案内所などの観光関連データ。"
    },
    "bosai": {
        "title": "防災",
        "description": "台東区の避難所、公衆トイレなどの災害対策・安全関連データ。"
    },
    "sports": {
        "title": "スポーツ",
        "description": "台東区のスポーツ施設、体育館、運動場などのスポーツ関連データ。"
    },
    "infra": {
        "title": "インフラ・まちづくり",
        "description": "台東区の都市公園、公衆喫煙所、公衆無線LANなどの都市インフラ関連データ。"
    }
}

class STACBuilder:
    def __init__(self, base_url: str = "http://localhost:8082/stac"):
        self.base_url = base_url.rstrip("/")

    def get_collection_id(self, dataset: Dict[str, Any]) -> str:
        """
        Map a CKAN dataset to a STAC Collection ID based on title or tags.
        """
        title = dataset.get("title", "")
        notes = dataset.get("notes", "") or ""
        
        # Match keywords to collection IDs
        if any(kw in title for kw in ["避難所", "防災", "災害"]):
            return "bosai"
        elif any(kw in title for kw in ["子ども食堂", "子供", "教育", "図書館"]):
            # Split library to bunka if preferred, let's keep library in library/bunka
            if "図書館" in title:
                return "bunka-geijutsu"
            return "kodomo-kyoiku"
        elif any(kw in title for kw in ["スポーツ", "体育", "運動"]):
            return "sports"
        elif any(kw in title for kw in ["公園", "喫煙所", "無線LAN", "Wi-Fi"]):
            return "infra"
        elif any(kw in title for kw in ["文化財", "博物館", "美術館", "芸術"]):
            return "bunka-geijutsu"
        elif any(kw in title for kw in ["宿泊施設", "旅館", "ホテル", "観光"]):
            return "kanko"
        elif any(kw in title for kw in ["食品", "美容", "理容", "クリーニング", "銭湯", "薬局", "病院"]):
            return "kenko-iryo"
        else:
            return "kurashi-sumai"

    def compute_bbox_and_geometry(self, geojson: Dict[str, Any]) -> Tuple[List[float], Dict[str, Any]]:
        """
        Compute the overall bounding box and Polygon geometry from a GeoJSON FeatureCollection.
        """
        features = geojson.get("features", [])
        if not features:
            bbox = TAITO_BBOX
        else:
            lons = []
            lats = []
            for f in features:
                coords = f.get("geometry", {}).get("coordinates", [])
                if coords and len(coords) >= 2:
                    lons.append(coords[0])
                    lats.append(coords[1])
            
            if lons and lats:
                bbox = [min(lons), min(lats), max(lons), max(lats)]
            else:
                bbox = TAITO_BBOX

        # Handle point-like bounding boxes (min == max)
        if bbox[0] == bbox[2]:
            bbox[0] -= 0.001
            bbox[2] += 0.001
        if bbox[1] == bbox[3]:
            bbox[1] -= 0.001
            bbox[3] += 0.001

        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [bbox[0], bbox[1]],
                [bbox[2], bbox[1]],
                [bbox[2], bbox[3]],
                [bbox[0], bbox[3]],
                [bbox[0], bbox[1]]
            ]]
        }
        return bbox, geometry

    def build_collection(self, collection_id: str) -> Dict[str, Any]:
        """
        Build a STAC Collection metadata object.
        """
        info = STAC_COLLECTIONS_INFO.get(collection_id, {
            "title": "その他施設情報",
            "description": "台東区の各種施設情報データ。"
        })
        
        return {
            "type": "Collection",
            "stac_version": "1.0.0",
            "id": collection_id,
            "title": info["title"],
            "description": info["description"],
            "license": "CC-BY-4.0",
            "extent": {
                "spatial": {
                    "bbox": [TAITO_BBOX]
                },
                "temporal": {
                    "interval": [["2020-01-01T00:00:00Z", None]]
                }
            },
            "providers": [
                {
                    "name": "東京都台東区",
                    "roles": ["licensor", "producer"],
                    "url": "https://www.city.taito.lg.jp/"
                }
            ],
            "links": [
                {
                    "rel": "self",
                    "href": f"{self.base_url}/collections/{collection_id}",
                    "type": "application/json"
                },
                {
                    "rel": "parent",
                    "href": f"{self.base_url}/",
                    "type": "application/json"
                },
                {
                    "rel": "root",
                    "href": f"{self.base_url}/",
                    "type": "application/json"
                },
                {
                    "rel": "items",
                    "href": f"{self.base_url}/collections/{collection_id}/items",
                    "type": "application/geo+json"
                }
            ]
        }

    def build_item(
        self,
        dataset: Dict[str, Any],
        geojson: Dict[str, Any],
        geojson_url: str,
        csv_url: str
    ) -> Dict[str, Any]:
        """
        Build a STAC Item representing a single CKAN dataset.
        """
        dataset_id = dataset.get("name", "dataset")
        collection_id = self.get_collection_id(dataset)
        
        bbox, geometry = self.compute_bbox_and_geometry(geojson)
        
        # Datetime processing
        modified_str = dataset.get("metadata_modified", "")
        dt_obj = None
        if modified_str:
            try:
                # Common formats: 2024-03-12T05:32:11.234567, 2024-03-12T05:32:11Z, etc.
                # Remove microseconds/Z first for simplified ISO parsing
                clean_dt = modified_str.split(".")[0].rstrip("Z")
                dt_obj = datetime.fromisoformat(clean_dt).replace(tzinfo=timezone.utc)
            except Exception:
                pass
                
        if not dt_obj:
            dt_obj = datetime.now(timezone.utc)
            
        dt_formatted = dt_obj.isoformat().replace("+00:00", "Z")

        # Build Assets
        assets = {
            "geojson": {
                "href": geojson_url,
                "type": "application/geo+json",
                "title": f"{dataset.get('title')} (GeoJSON FeatureCollection)",
                "roles": ["data"]
            }
        }
        
        if csv_url:
            assets["source_csv"] = {
                "href": csv_url,
                "type": "text/csv",
                "title": "元データ (CSV)",
                "roles": ["source"]
            }

        item = {
            "type": "Feature",
            "stac_version": "1.0.0",
            "id": dataset_id,
            "collection": collection_id,
            "geometry": geometry,
            "bbox": bbox,
            "properties": {
                "title": dataset.get("title"),
                "description": dataset.get("notes") or "",
                "datetime": dt_formatted,
                "license": "CC-BY-4.0",
                "updated": dt_formatted
            },
            "assets": assets,
            "links": [
                {
                    "rel": "self",
                    "href": f"{self.base_url}/collections/{collection_id}/items/{dataset_id}",
                    "type": "application/geo+json"
                },
                {
                    "rel": "parent",
                    "href": f"{self.base_url}/collections/{collection_id}",
                    "type": "application/json"
                },
                {
                    "rel": "collection",
                    "href": f"{self.base_url}/collections/{collection_id}",
                    "type": "application/json"
                },
                {
                    "rel": "root",
                    "href": f"{self.base_url}/",
                    "type": "application/json"
                }
            ]
        }
        
        return item

    def save_stac_data(self, collections: List[Dict[str, Any]], items: List[Dict[str, Any]]):
        """
        Save the generated STAC Collections and Items JSONs locally so the server can load them.
        """
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        items_dir = DATA_DIR / "items"
        items_dir.mkdir(parents=True, exist_ok=True)
        
        # Save Collections
        with open(DATA_DIR / "collections.json", "w", encoding="utf-8") as f:
            json.dump(collections, f, ensure_ascii=False, indent=2)
            
        # Save individual Items
        for item in items:
            item_id = item["id"]
            with open(items_dir / f"{item_id}.json", "w", encoding="utf-8") as f:
                json.dump(item, f, ensure_ascii=False, indent=2)
                
        logger.info(f"Saved {len(collections)} collections and {len(items)} items to {DATA_DIR}")
