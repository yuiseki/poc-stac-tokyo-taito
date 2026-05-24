import pytest
from fastapi.testclient import TestClient
from poc_stac_tokyo_taito.app import app, collections_db, items_db

@pytest.fixture(autouse=True)
def setup_test_db():
    # Setup standard test collections and items in-memory
    collections_db.clear()
    items_db.clear()
    
    collections_db["bosai"] = {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": "bosai",
        "title": "防災",
        "description": "防災データ",
        "license": "CC-BY-4.0",
        "extent": {
            "spatial": {"bbox": [[139.76, 35.69, 139.81, 35.74]]},
            "temporal": {"interval": [["2020-01-01T00:00:00Z", None]]}
        },
        "providers": [],
        "links": []
    }
    
    items_db["item1"] = {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": "item1",
        "collection": "bosai",
        "bbox": [139.78, 35.71, 139.79, 35.72],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[139.78, 35.71], [139.79, 35.71], [139.79, 35.72], [139.78, 35.72], [139.78, 35.71]]]
        },
        "properties": {
            "title": "テスト避難所",
            "datetime": "2024-03-12T05:32:11Z"
        },
        "assets": {},
        "links": []
    }

client = TestClient(app)

def test_landing_page():
    response = client.get("/stac/")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "Catalog"
    assert data["id"] == "poc-stac-tokyo-taito"
    # Verify child collection link is present
    assert any(link["rel"] == "child" and "bosai" in link["href"] for link in data["links"])

def test_conformance():
    response = client.get("/stac/conformance")
    assert response.status_code == 200
    data = response.json()
    assert "conformsTo" in data
    assert "https://api.stacspec.org/v1.0.0/core" in data["conformsTo"]

def test_get_collections():
    response = client.get("/stac/collections")
    assert response.status_code == 200
    data = response.json()
    assert len(data["collections"]) == 1
    assert data["collections"][0]["id"] == "bosai"

def test_get_collection():
    # Success
    response = client.get("/stac/collections/bosai")
    assert response.status_code == 200
    assert response.json()["id"] == "bosai"
    
    # 404 Failure
    response_404 = client.get("/stac/collections/nonexistent")
    assert response_404.status_code == 404

def test_get_collection_items():
    # Success without query
    response = client.get("/stac/collections/bosai/items")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1
    assert data["features"][0]["id"] == "item1"
    
    # Success with spatial bbox query (intersects item)
    response_bbox = client.get("/stac/collections/bosai/items?bbox=139.77,35.70,139.80,35.73")
    assert response_bbox.status_code == 200
    assert len(response_bbox.json()["features"]) == 1
    
    # Success with spatial bbox query (completely outside)
    response_bbox_empty = client.get("/stac/collections/bosai/items?bbox=139.0,35.0,139.1,35.1")
    assert response_bbox_empty.status_code == 200
    assert len(response_bbox_empty.json()["features"]) == 0

def test_get_collection_item():
    # Success
    response = client.get("/stac/collections/bosai/items/item1")
    assert response.status_code == 200
    assert response.json()["id"] == "item1"
    
    # 404
    response_404 = client.get("/stac/collections/bosai/items/nonexistent")
    assert response_404.status_code == 404

def test_search_get():
    # bbox overlap
    response = client.get("/stac/search?bbox=139.77,35.70,139.80,35.73")
    assert response.status_code == 200
    assert len(response.json()["features"]) == 1
    
    # datetime overlap
    response_dt = client.get("/stac/search?datetime=2024-03-01T00:00:00Z/2024-04-01T00:00:00Z")
    assert response_dt.status_code == 200
    assert len(response_dt.json()["features"]) == 1
    
    # datetime outside
    response_dt_empty = client.get("/stac/search?datetime=2024-01-01T00:00:00Z/2024-02-01T00:00:00Z")
    assert response_dt_empty.status_code == 200
    assert len(response_dt_empty.json()["features"]) == 0

def test_search_post():
    # Search request body
    search_req = {
        "bbox": [139.77, 35.70, 139.80, 35.73],
        "collections": ["bosai"],
        "datetime": "2024-03-01T00:00:00Z/2024-04-01T00:00:00Z"
    }
    response = client.post("/stac/search", json=search_req)
    assert response.status_code == 200
    assert len(response.json()["features"]) == 1

def test_vector_tile_endpoint():
    from geojson2vt.geojson2vt import geojson2vt
    import poc_stac_tokyo_taito.app as app_mod
    
    geojson_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [139.7810, 35.7138]
                },
                "properties": {
                    "name": "Taito-ku Office",
                    "collection": "infra"
                }
            }
        ]
    }
    app_mod.combined_tile_index = geojson2vt(geojson_data, {
        'maxZoom': 14,
        'tolerance': 3,
        'extent': 4096,
        'buffer': 64
    })
    
    # Try fetching tile (0, 0, 0)
    response = client.get("/tiles/0/0/0")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert len(response.content) > 0
    
    # Try fetching tile that does not exist/is empty
    response_empty = client.get("/tiles/14/0/0")
    assert response_empty.status_code == 200
    assert response_empty.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    
    # Clean up
    app_mod.combined_tile_index = None

def test_state_tile_endpoint():
    import poc_stac_tokyo_taito.app as app_mod
    from poc_stac_tokyo_taito.megurin_simulator import MegurinSimulator
    from poc_stac_tokyo_taito.config import DATA_DIR
    
    # Ensure megurin_simulator is initialized
    if app_mod.megurin_simulator is None:
        app_mod.megurin_simulator = MegurinSimulator(DATA_DIR / "megurin")

    # Fetch tile for midday (12:00 PM) during peak operational hours
    response = client.get("/state/14/14549/6438?seconds=43200")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert "no-cache" in response.headers["cache-control"]
    
    # Test query by formatted time hh:mm:ss
    response_time = client.get("/state/14/14549/6438?t=12:00:00")
    assert response_time.status_code == 200
    assert response_time.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert "no-cache" in response_time.headers["cache-control"]

    # Test query during midnight where zero buses are running (should return empty tile or 200)
    response_midnight = client.get("/state/14/14549/6438?seconds=7200")
    assert response_midnight.status_code == 200
    assert response_midnight.headers["content-type"] == "application/vnd.mapbox-vector-tile"


def test_state_buses_endpoint():
    import poc_stac_tokyo_taito.app as app_mod
    from poc_stac_tokyo_taito.megurin_simulator import MegurinSimulator
    from poc_stac_tokyo_taito.config import DATA_DIR
    
    if app_mod.megurin_simulator is None:
        app_mod.megurin_simulator = MegurinSimulator(DATA_DIR / "megurin")

    # Midday
    response = client.get("/state/buses?seconds=43200")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) > 0

    # Midnight
    response_midnight = client.get("/state/buses?seconds=7200")
    assert response_midnight.status_code == 200
    assert len(response_midnight.json()["features"]) == 0


