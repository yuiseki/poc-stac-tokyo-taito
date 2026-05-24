import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from poc_stac_tokyo_taito.geojson_converter import GeoJSONConverter

@pytest.mark.asyncio
async def test_records_to_geojson_with_existing_coordinates():
    geocoder_mock = MagicMock()
    geocoder_mock.geocode = AsyncMock()
    
    converter = GeoJSONConverter(geocoder=geocoder_mock)
    records = [
        {
            "名称": "テストスポーツ施設",
            "所在地_連結表記": "台東区東上野4-5-6",
            "緯度": "35.715",
            "経度": "139.785"
        }
    ]
    
    geojson = await converter.records_to_geojson(records)
    
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 1
    
    feature = geojson["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    assert feature["geometry"]["coordinates"] == [139.785, 35.715]
    assert feature["properties"]["名称"] == "テストスポーツ施設"
    assert feature["properties"]["_resolved_address"] == "東京都台東区東上野4-5-6"
    assert feature["properties"]["_geocoded_fallback"] is False
    
    # Geocoder should NOT have been called because coordinates were present
    geocoder_mock.geocode.assert_not_called()

@pytest.mark.asyncio
async def test_records_to_geojson_triggers_geocoder():
    geocoder_mock = MagicMock()
    # Mock return values for geocode: (lon, lat, is_fallback)
    geocoder_mock.geocode = AsyncMock(return_value=(139.78, 35.71, False))
    
    converter = GeoJSONConverter(geocoder=geocoder_mock)
    records = [
        {
            "名称": "テスト子ども食堂",
            "所在地_連結表記": "台東区浅草1-1-1"
        }
    ]
    
    geojson = await converter.records_to_geojson(records)
    
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 1
    
    feature = geojson["features"][0]
    assert feature["geometry"]["coordinates"] == [139.78, 35.71]
    assert feature["properties"]["_resolved_address"] == "東京都台東区浅草1-1-1"
    assert feature["properties"]["_geocoded_fallback"] is False
    
    # Geocoder should have been called
    geocoder_mock.geocode.assert_called_once_with("東京都台東区浅草1-1-1")

def test_save_geojson(tmp_path, monkeypatch):
    # Override DOCS_DATA_DIR to point to tmp_path
    import poc_stac_tokyo_taito.geojson_converter
    monkeypatch.setattr(poc_stac_tokyo_taito.geojson_converter, "DOCS_DATA_DIR", tmp_path)
    
    geocoder_mock = MagicMock()
    converter = GeoJSONConverter(geocoder=geocoder_mock)
    
    geojson = {
        "type": "FeatureCollection",
        "features": []
    }
    
    saved_path = converter.save_geojson("test_dataset", geojson)
    
    expected_path = tmp_path / "test_dataset.geojson"
    assert Path(saved_path) == expected_path
    assert expected_path.exists()
    
    with open(expected_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
        assert loaded == geojson
