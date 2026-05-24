import pytest
import json
from pathlib import Path
from poc_stac_tokyo_taito.stac_builder import STACBuilder, STAC_COLLECTIONS_INFO
from poc_stac_tokyo_taito.config import TAITO_BBOX

def test_get_collection_id():
    builder = STACBuilder()
    
    assert builder.get_collection_id({"title": "台東区 避難所一覧"}) == "bosai"
    assert builder.get_collection_id({"title": "台東区 子ども食堂"}) == "kodomo-kyoiku"
    assert builder.get_collection_id({"title": "台東区 都市公園"}) == "infra"
    assert builder.get_collection_id({"title": "台東区 宿泊施設一覧"}) == "kanko"
    assert builder.get_collection_id({"title": "台東区 クリーニング所台帳"}) == "kenko-iryo"
    assert builder.get_collection_id({"title": "何でもないデータセット"}) == "kurashi-sumai"

def test_compute_bbox_and_geometry():
    builder = STACBuilder()
    
    # Simple coordinates
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {"geometry": {"coordinates": [139.78, 35.71]}},
            {"geometry": {"coordinates": [139.79, 35.72]}}
        ]
    }
    
    bbox, geometry = builder.compute_bbox_and_geometry(geojson)
    
    assert bbox == [139.78, 35.71, 139.79, 35.72]
    assert geometry["type"] == "Polygon"
    assert geometry["coordinates"][0][0] == [139.78, 35.71]
    assert geometry["coordinates"][0][2] == [139.79, 35.72]

def test_build_collection():
    builder = STACBuilder("http://test-stac-api.com")
    col = builder.build_collection("bosai")
    
    assert col["id"] == "bosai"
    assert col["type"] == "Collection"
    assert col["license"] == "CC-BY-4.0"
    assert any(link["rel"] == "self" and "http://test-stac-api.com/collections/bosai" in link["href"] for link in col["links"])

def test_build_item():
    builder = STACBuilder("http://test-stac-api.com")
    dataset = {
        "name": "t131067d0001",
        "title": "避難所一覧",
        "notes": "台東区の避難所の一覧です。",
        "metadata_modified": "2024-03-12T05:32:11.123Z"
    }
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {"geometry": {"coordinates": [139.78, 35.71]}}
        ]
    }
    
    item = builder.build_item(
        dataset=dataset,
        geojson=geojson,
        geojson_url="http://test-stac-api.com/docs/data/t131067d0001.geojson",
        csv_url="https://example.com/source.csv"
    )
    
    assert item["id"] == "t131067d0001"
    assert item["collection"] == "bosai"
    assert item["properties"]["title"] == "避難所一覧"
    assert "2024-03-12T05:32:11" in item["properties"]["datetime"]
    assert item["assets"]["geojson"]["href"] == "http://test-stac-api.com/docs/data/t131067d0001.geojson"
    assert item["assets"]["source_csv"]["href"] == "https://example.com/source.csv"

def test_save_stac_data(tmp_path, monkeypatch):
    import poc_stac_tokyo_taito.stac_builder
    # Override DATA_DIR to use tmp_path
    monkeypatch.setattr(poc_stac_tokyo_taito.stac_builder, "DATA_DIR", tmp_path)
    
    builder = STACBuilder()
    
    collections = [{"id": "bosai"}]
    items = [{"id": "item1", "collection": "bosai"}]
    
    builder.save_stac_data(collections, items)
    
    # Assert collection.json exists
    assert (tmp_path / "collections.json").exists()
    with open(tmp_path / "collections.json", "r") as f:
        col_data = json.load(f)
        assert col_data == collections
        
    # Assert item1.json exists
    assert (tmp_path / "items" / "item1.json").exists()
    with open(tmp_path / "items" / "item1.json", "r") as f:
        item_data = json.load(f)
        assert item_data == items[0]
