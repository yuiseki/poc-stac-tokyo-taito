import pytest
from geojson2vt.geojson2vt import geojson2vt
from vt2pbf import vt2pbf

def test_geojson_to_mvt():
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
    
    tile_index = geojson2vt(geojson_data, {
        'maxZoom': 14,
        'tolerance': 3,
        'extent': 4096,
        'buffer': 64
    })
    
    tile = tile_index.get_tile(0, 0, 0)
    assert tile is not None
    assert "features" in tile
    
    pbf_data = vt2pbf(tile)
    assert isinstance(pbf_data, bytes)
    assert len(pbf_data) > 0

def test_geojson_string_id_handling():
    # String ID feature causes TypeError in vt2pbf
    geojson_string_id = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "some-string-id",
                "geometry": {
                    "type": "Point",
                    "coordinates": [139.7810, 35.7138]
                },
                "properties": {
                    "name": "Taito-ku Office"
                }
            }
        ]
    }
    
    tile_index = geojson2vt(geojson_string_id, {'maxZoom': 14})
    tile = tile_index.get_tile(0, 0, 0)
    assert tile is not None
    
    with pytest.raises(TypeError):
        vt2pbf(tile)

    # Applying the sanitization logic allows vt2pbf to succeed
    import zlib
    for feat in tile.get("features", []):
        if "id" in feat:
            try:
                feat["id"] = int(feat["id"])
            except (ValueError, TypeError):
                feat["id"] = zlib.adler32(str(feat["id"]).encode('utf-8')) & 0xFFFFFFFF

    pbf_data = vt2pbf(tile)
    assert isinstance(pbf_data, bytes)
    assert len(pbf_data) > 0

