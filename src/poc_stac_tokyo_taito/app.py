import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query, Response, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from dateutil.parser import parse as parse_date

from poc_stac_tokyo_taito.config import DATA_DIR, BASE_DIR
from poc_stac_tokyo_taito.models import (
    StacCatalog, StacCollection, StacItem, StacLink, StacSearchRequest
)
from poc_stac_tokyo_taito.megurin_simulator import MegurinSimulator, time_to_seconds

logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_stac_data()
    yield

app = FastAPI(
    title="台東区オープンデータ STAC API POC",
    description="台東区オープンデータをGeoJSON化し、STAC API規格に準拠して提供するAPI",
    version="0.1.0",
    lifespan=lifespan
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles

# Mount /viewer to serve docs folder containing index.html and data/
docs_dir = BASE_DIR / "docs"
if docs_dir.exists():
    app.mount("/viewer", StaticFiles(directory=docs_dir, html=True), name="viewer")

stac_router = APIRouter()

def replace_base_url(data: Any, target_base_url: str) -> Any:
    """
    Recursively replace 'http://localhost:8000' (or other potential base URLs)
    with the actual request-based base URL (e.g., 'http://localhost:8082/stac').
    """
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            if k == "href" and isinstance(v, str):
                # Replace the old base URL with the new one
                if v.startswith("http://localhost:8000/collections"):
                    new_dict[k] = v.replace("http://localhost:8000", target_base_url)
                elif v.startswith("http://localhost:8000/search"):
                    new_dict[k] = v.replace("http://localhost:8000", target_base_url)
                elif v.startswith("http://localhost:8000/"):
                    new_dict[k] = v.replace("http://localhost:8000", target_base_url)
                elif v.startswith("http://localhost:8082/stac/collections"):
                    new_dict[k] = v.replace("http://localhost:8082/stac", target_base_url)
                elif v.startswith("http://localhost:8082/stac/search"):
                    new_dict[k] = v.replace("http://localhost:8082/stac", target_base_url)
                elif v.startswith("http://localhost:8082/stac/"):
                    new_dict[k] = v.replace("http://localhost:8082/stac", target_base_url)
                else:
                    new_dict[k] = v
            else:
                new_dict[k] = replace_base_url(v, target_base_url)
        return new_dict
    elif isinstance(data, list):
        return [replace_base_url(item, target_base_url) for item in data]
    else:
        return data

# Global in-memory STAC storage
collections_db: Dict[str, Dict[str, Any]] = {}
items_db: Dict[str, Dict[str, Any]] = {}
combined_tile_index = None
megurin_simulator = None

def load_stac_data():
    """Load STAC collections and items from disk into memory."""
    global collections_db, items_db, combined_tile_index, megurin_simulator
    collections_db.clear()
    items_db.clear()
    
    # Load Megurin simulator
    try:
        megurin_simulator = MegurinSimulator(DATA_DIR / "megurin")
        logger.info("Megurin simulator initialized successfully in app lifespan.")
    except Exception as e:
        logger.error(f"Failed to initialize Megurin simulator in app lifespan: {e}")
        megurin_simulator = None
    
    # Load Collections
    col_file = DATA_DIR / "collections.json"
    if col_file.exists():
        try:
            with open(col_file, "r", encoding="utf-8") as f:
                cols = json.load(f)
                for col in cols:
                    collections_db[col["id"]] = col
            logger.info(f"Loaded {len(collections_db)} collections into STAC API.")
        except Exception as e:
            logger.error(f"Failed to load collections: {e}")
            
    # Load Items
    items_dir = DATA_DIR / "items"
    if items_dir.exists():
        try:
            for fpath in items_dir.glob("*.json"):
                with open(fpath, "r", encoding="utf-8") as f:
                    item = json.load(f)
                    items_db[item["id"]] = item
            logger.info(f"Loaded {len(items_db)} items into STAC API.")
        except Exception as e:
            logger.error(f"Failed to load items: {e}")

    # Merge all GeoJSON datasets and build tile index for MVT
    combined_geojson = {
        "type": "FeatureCollection",
        "features": []
    }
    
    feature_id_counter = 1
    for item_id, item in items_db.items():
        collection_id = item.get("collection")
        dataset_title = item.get("properties", {}).get("title", item_id)
        
        geojson_path = BASE_DIR / "docs" / "data" / f"{item_id}.geojson"
        if geojson_path.exists():
            try:
                with open(geojson_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for feat in data.get("features", []):
                        props = feat.get("properties", {})
                        if "id" in feat:
                            props["original_id"] = feat["id"]
                        feat["id"] = feature_id_counter
                        feature_id_counter += 1
                        
                        props["dataset_id"] = item_id
                        props["collection_id"] = collection_id
                        props["dataset_title"] = dataset_title
                        feat["properties"] = props
                        combined_geojson["features"].append(feat)
            except Exception as e:
                logger.error(f"Failed to load GeoJSON for dynamic tiles from {geojson_path}: {e}")
                
    if combined_geojson["features"]:
        try:
            from geojson2vt.geojson2vt import geojson2vt
            combined_tile_index = geojson2vt(combined_geojson, {
                'maxZoom': 18,
                'tolerance': 3,
                'extent': 4096,
                'buffer': 64
            })
            logger.info(f"Built dynamic MVT tile index with {len(combined_geojson['features'])} features.")
        except Exception as e:
            logger.error(f"Failed to build tile index: {e}")
            combined_tile_index = None
    else:
        combined_tile_index = None

# Lifespan handles loading now

def parse_datetime_query(dt_str: str) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Parse STAC datetime query parameter (RFC 3339).
    Can be a single timestamp or an interval like start/end, start/.., ../end
    """
    if not dt_str:
        return None, None
        
    if "/" not in dt_str:
        try:
            dt = parse_date(dt_str)
            return dt, dt
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid datetime format: {dt_str}")
            
    parts = dt_str.split("/")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail=f"Invalid datetime interval format: {dt_str}")
        
    start_str, end_str = parts[0], parts[1]
    
    start_dt = None
    if start_str and start_str != "..":
        try:
            start_dt = parse_date(start_str)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid start datetime: {start_str}")
            
    end_dt = None
    if end_str and end_str != "..":
        try:
            end_dt = parse_date(end_str)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid end datetime: {end_str}")
            
    return start_dt, end_dt

def filter_items(
    bbox: Optional[List[float]] = None,
    datetime_str: Optional[str] = None,
    collections: Optional[List[str]] = None,
    ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Helper to filter memory-loaded items based on STAC parameters."""
    filtered = list(items_db.values())
    
    # 1. Filter by Collection IDs
    if collections:
        filtered = [item for item in filtered if item.get("collection") in collections]
        
    # 2. Filter by Item IDs
    if ids:
        filtered = [item for item in filtered if item.get("id") in ids]
        
    # 3. Filter by Spatial Bounding Box
    if bbox:
        if len(bbox) != 4:
            raise HTTPException(status_code=400, detail="Bbox must contain exactly 4 values: [min_lon, min_lat, max_lon, max_lat]")
        minx, miny, maxx, maxy = bbox
        
        intersected = []
        for item in filtered:
            item_bbox = item.get("bbox")
            if not item_bbox or len(item_bbox) != 4:
                continue
            imin_lon, imin_lat, imax_lon, imax_lat = item_bbox
            
            # Check overlap
            if (minx <= imax_lon and maxx >= imin_lon and
                miny <= imax_lat and maxy >= imin_lat):
                intersected.append(item)
        filtered = intersected
        
    # 4. Filter by Temporal Datetime
    if datetime_str:
        start_dt, end_dt = parse_datetime_query(datetime_str)
        
        timed = []
        for item in filtered:
            dt_prop = item.get("properties", {}).get("datetime")
            if not dt_prop:
                continue
            try:
                item_dt = parse_date(dt_prop)
                
                # Check within interval
                if start_dt and end_dt:
                    if start_dt <= item_dt <= end_dt:
                        timed.append(item)
                elif start_dt:
                    if item_dt >= start_dt:
                        timed.append(item)
                elif end_dt:
                    if item_dt <= end_dt:
                        timed.append(item)
            except Exception:
                continue
        filtered = timed
        
    return filtered

def geojson_response(content: Any) -> Response:
    """Helper to return GeoJSON response with proper headers."""
    return Response(
        content=json.dumps(content, ensure_ascii=False, indent=2),
        media_type="application/geo+json"
    )

@stac_router.get("/", response_model=StacCatalog)
def get_landing_page(request: Request):
    """STAC Landing Page (Root Catalog)"""
    base_url = str(request.base_url).rstrip("/") + "/stac"
    
    links = [
        StacLink(rel="self", href=f"{base_url}/", type="application/json", title="Landing Page"),
        StacLink(rel="conformance", href=f"{base_url}/conformance", type="application/json", title="Conformance Classes"),
        StacLink(rel="search", href=f"{base_url}/search", type="application/geo+json", title="STAC Search Endpoint (GET)"),
        StacLink(rel="search", href=f"{base_url}/search", type="application/geo+json", title="STAC Search Endpoint (POST)")
    ]
    
    # Add Collection links
    for col_id in collections_db.keys():
        links.append(StacLink(
            rel="child",
            href=f"{base_url}/collections/{col_id}",
            type="application/json",
            title=collections_db[col_id].get("title", col_id)
        ))
        
    return StacCatalog(links=links)

@stac_router.get("/conformance")
def get_conformance():
    """STAC Conformance Endpoint"""
    return {
        "conformsTo": [
            "https://api.stacspec.org/v1.0.0/core",
            "https://api.stacspec.org/v1.0.0/collections",
            "https://api.stacspec.org/v1.0.0/ogcapi-features",
            "https://api.stacspec.org/v1.0.0/item-search",
            "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
            "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson"
        ]
    }

@stac_router.get("/collections")
def get_collections(request: Request):
    """List all available STAC Collections"""
    base_url = str(request.base_url).rstrip("/") + "/stac"
    replaced_collections = [replace_base_url(col, base_url) for col in collections_db.values()]
    return {
        "collections": replaced_collections,
        "links": [
            StacLink(rel="self", href=f"{base_url}/collections", type="application/json").model_dump(),
            StacLink(rel="root", href=f"{base_url}/", type="application/json").model_dump()
        ]
    }

@stac_router.get("/collections/{collection_id}", response_model=StacCollection)
def get_collection(collection_id: str, request: Request):
    """Get metadata for a single STAC Collection"""
    if collection_id not in collections_db:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found.")
    base_url = str(request.base_url).rstrip("/") + "/stac"
    return replace_base_url(collections_db[collection_id], base_url)

@stac_router.get("/collections/{collection_id}/items")
def get_collection_items(
    collection_id: str,
    request: Request,
    bbox: Optional[str] = Query(None, description="Bounding box in min_lon,min_lat,max_lon,max_lat format"),
    datetime: Optional[str] = Query(None, description="Datetime filter (RFC 3339)"),
    limit: int = Query(10, ge=1, le=1000)
):
    """List STAC Items belonging to a specific Collection"""
    if collection_id not in collections_db:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found.")
        
    bbox_list = None
    if bbox:
        try:
            bbox_list = [float(x) for x in bbox.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="Bbox must be comma-separated float list")
            
    filtered = filter_items(bbox=bbox_list, datetime_str=datetime, collections=[collection_id])
    
    # Simple pagination limit
    sliced = filtered[:limit]
    
    base_url = str(request.base_url).rstrip("/") + "/stac"
    replaced_features = [replace_base_url(item, base_url) for item in sliced]
    
    feature_collection = {
        "type": "FeatureCollection",
        "features": replaced_features,
        "links": [
            {"rel": "self", "href": f"{base_url}/collections/{collection_id}/items", "type": "application/geo+json"},
            {"rel": "parent", "href": f"{base_url}/collections/{collection_id}", "type": "application/json"},
            {"rel": "root", "href": f"{base_url}/", "type": "application/json"}
        ]
    }
    
    return geojson_response(feature_collection)

@stac_router.get("/collections/{collection_id}/items/{item_id}", response_model=StacItem)
def get_collection_item(collection_id: str, item_id: str, request: Request):
    """Get a single STAC Item"""
    if collection_id not in collections_db:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found.")
        
    item = items_db.get(item_id)
    if not item or item.get("collection") != collection_id:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found in collection '{collection_id}'.")
        
    base_url = str(request.base_url).rstrip("/") + "/stac"
    return replace_base_url(item, base_url)

@stac_router.get("/search")
def search_items_get(
    request: Request,
    bbox: Optional[str] = Query(None, description="Bounding box [min_lon, min_lat, max_lon, max_lat]"),
    datetime: Optional[str] = Query(None, description="Temporal query (RFC 3339)"),
    collections: Optional[str] = Query(None, description="Comma-separated collection IDs"),
    ids: Optional[str] = Query(None, description="Comma-separated item IDs"),
    limit: int = Query(10, ge=1, le=1000)
):
    """STAC Search GET Endpoint"""
    bbox_list = None
    if bbox:
        try:
            bbox_list = [float(x) for x in bbox.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="Bbox must be comma-separated floats")
            
    col_list = collections.split(",") if collections else None
    id_list = ids.split(",") if ids else None
    
    results = filter_items(bbox=bbox_list, datetime_str=datetime, collections=col_list, ids=id_list)
    sliced = results[:limit]
    
    base_url = str(request.base_url).rstrip("/") + "/stac"
    replaced_features = [replace_base_url(item, base_url) for item in sliced]
    
    feature_collection = {
        "type": "FeatureCollection",
        "stac_version": "1.0.0",
        "stac_extensions": [],
        "context": {
            "returned": len(sliced),
            "matched": len(results),
            "limit": limit
        },
        "features": replaced_features,
        "links": [
            {"rel": "self", "href": f"{base_url}/search", "type": "application/geo+json"}
        ]
    }
    return geojson_response(feature_collection)

@stac_router.post("/search")
def search_items_post(request_body: StacSearchRequest, request: Request):
    """STAC Search POST Endpoint"""
    results = filter_items(
        bbox=request_body.bbox,
        datetime_str=request_body.datetime,
        collections=request_body.collections,
        ids=request_body.ids
    )
    
    limit = request_body.limit or 10
    sliced = results[:limit]
    
    base_url = str(request.base_url).rstrip("/") + "/stac"
    replaced_features = [replace_base_url(item, base_url) for item in sliced]
    
    feature_collection = {
        "type": "FeatureCollection",
        "stac_version": "1.0.0",
        "stac_extensions": [],
        "context": {
            "returned": len(sliced),
            "matched": len(results),
            "limit": limit
        },
        "features": replaced_features,
        "links": [
            {"rel": "self", "href": f"{base_url}/search", "type": "application/geo+json"}
        ]
    }
    return geojson_response(feature_collection)

# Register STAC router with /stac prefix
app.include_router(stac_router, prefix="/stac")

@app.get("/tiles/{z}/{x}/{y}")
def get_vector_tile(z: int, x: int, y: int):
    """
    Serve dynamic Mapbox Vector Tiles (MVT) containing all merged features.
    """
    global combined_tile_index
    if combined_tile_index is None:
        return Response(
            content=b"",
            status_code=503,
            media_type="application/vnd.mapbox-vector-tile"
        )
        
    try:
        tile = combined_tile_index.get_tile(z, x, y)
        if not tile:
            # Return an empty tile
            return Response(
                content=b"",
                media_type="application/vnd.mapbox-vector-tile"
            )
            
        # Sanitize feature IDs in the tile output to be integers.
        # geojson2vt can convert feature IDs to strings internally, and vt2pbf
        # strictly requires integer feature IDs.
        import zlib
        for feat in tile.get("features", []):
            if "id" in feat:
                try:
                    feat["id"] = int(feat["id"])
                except (ValueError, TypeError):
                    feat["id"] = zlib.adler32(str(feat["id"]).encode('utf-8')) & 0xFFFFFFFF

        from vt2pbf import vt2pbf
        pbf_data = vt2pbf(tile)
        return Response(
            content=pbf_data,
            media_type="application/vnd.mapbox-vector-tile"
        )
    except Exception as e:
        logger.error(f"Error generating tile {z}/{x}/{y}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/state/buses")
def get_state_buses(
    t: Optional[str] = Query(None, description="Simulation time as hh:mm:ss"),
    seconds: Optional[int] = Query(None, description="Simulation time in seconds from midnight")
):
    """
    Get all simulated Megurin bus positions as a GeoJSON FeatureCollection.
    Useful for counting total active buses or lightweight direct querying.
    """
    global megurin_simulator
    if megurin_simulator is None or not megurin_simulator.is_loaded:
        return Response(
            content=json.dumps({"type": "FeatureCollection", "features": []}),
            status_code=503,
            media_type="application/json"
        )

    # Determine simulation seconds from midnight
    if seconds is not None:
        sim_seconds = seconds
    elif t is not None:
        sim_seconds = time_to_seconds(t)
    else:
        now = datetime.now()
        sim_seconds = now.hour * 3600 + now.minute * 60 + now.second

    try:
        geojson = megurin_simulator.get_bus_positions_geojson(sim_seconds)
        return Response(
            content=json.dumps(geojson, ensure_ascii=False),
            media_type="application/json",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )
    except Exception as e:
        logger.error(f"Error generating state buses JSON: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/state/{z}/{x}/{y}")
def get_state_vector_tile(
    z: int,
    x: int,
    y: int,
    t: Optional[str] = Query(None, description="Simulation time as hh:mm:ss"),
    seconds: Optional[int] = Query(None, description="Simulation time in seconds from midnight")
):
    """
    Serve dynamic real-time Mapbox Vector Tiles (MVT) containing Megurin bus coordinates.
    The time defaults to the current wall-clock time, but can be overridden for simulation/debugging.
    """
    global megurin_simulator
    if megurin_simulator is None or not megurin_simulator.is_loaded:
        return Response(
            content=b"",
            status_code=503,
            media_type="application/vnd.mapbox-vector-tile",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )

    # Determine simulation seconds from midnight
    if seconds is not None:
        sim_seconds = seconds
    elif t is not None:
        sim_seconds = time_to_seconds(t)
    else:
        now = datetime.now()
        sim_seconds = now.hour * 3600 + now.minute * 60 + now.second

    try:
        # Get simulated bus position GeoJSON
        geojson = megurin_simulator.get_bus_positions_geojson(sim_seconds)
        
        # Slices to MVT on-the-fly
        from geojson2vt.geojson2vt import geojson2vt
        tile_index = geojson2vt(geojson, {
            'maxZoom': 18,
            'tolerance': 3,
            'extent': 4096,
            'buffer': 64
        })

        tile = tile_index.get_tile(z, x, y)
        if not tile:
            # Return an empty tile
            return Response(
                content=b"",
                media_type="application/vnd.mapbox-vector-tile",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
            )

        # Sanitize feature IDs for vt2pbf
        import zlib
        for feat in tile.get("features", []):
            if "id" in feat:
                try:
                    feat["id"] = int(feat["id"])
                except (ValueError, TypeError):
                    feat["id"] = zlib.adler32(str(feat["id"]).encode('utf-8')) & 0xFFFFFFFF

        from vt2pbf import vt2pbf
        pbf_data = vt2pbf(tile)
        
        return Response(
            content=pbf_data,
            media_type="application/vnd.mapbox-vector-tile",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )
    except Exception as e:
        logger.error(f"Error generating state tile {z}/{x}/{y}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

