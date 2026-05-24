import pytest
from pathlib import Path
from poc_stac_tokyo_taito.config import DATA_DIR
from poc_stac_tokyo_taito.megurin_simulator import MegurinSimulator, time_to_seconds, seconds_to_time

def test_time_conversions():
    assert time_to_seconds("08:15:00") == 8 * 3600 + 15 * 60
    assert time_to_seconds("00:00:00") == 0
    assert time_to_seconds("25:00:00") == 25 * 3600
    assert time_to_seconds("invalid") == 0

    assert seconds_to_time(8 * 3600 + 15 * 60) == "08:15:00"
    assert seconds_to_time(0) == "00:00:00"

def test_megurin_simulator_load():
    megurin_dir = DATA_DIR / "megurin"
    assert megurin_dir.exists(), "Megurin GTFS data directory must exist"

    sim = MegurinSimulator(megurin_dir)
    assert sim.is_loaded
    assert len(sim.stops) > 0
    assert len(sim.routes) > 0
    assert len(sim.trips) > 0
    assert len(sim.stop_times_by_trip) > 0

def test_get_bus_positions_daytime():
    megurin_dir = DATA_DIR / "megurin"
    sim = MegurinSimulator(megurin_dir)
    
    # 10:00:00 AM (10 * 3600 = 36000 seconds) is peak operational hours for community buses
    current_seconds = 10 * 3600
    geojson = sim.get_bus_positions_geojson(current_seconds)
    
    assert geojson["type"] == "FeatureCollection"
    assert "features" in geojson
    
    # We should have some buses running during peak morning hours (10:00 AM)
    features = geojson["features"]
    assert len(features) > 0, "There should be active buses running at 10:00 AM"
    
    # Check structure of the first feature
    feat = features[0]
    assert feat["type"] == "Feature"
    assert "id" in feat
    assert feat["geometry"]["type"] == "Point"
    assert len(feat["geometry"]["coordinates"]) == 2
    
    props = feat["properties"]
    assert "trip_id" in props
    assert "route_id" in props
    assert "route_name" in props
    assert "route_color" in props
    assert "status" in props
    assert props["status"] in ["moving", "stopped"]
    assert "prev_stop_name" in props
    assert "next_stop_name" in props

def test_get_bus_positions_midnight():
    megurin_dir = DATA_DIR / "megurin"
    sim = MegurinSimulator(megurin_dir)
    
    # 2:00:00 AM (2 * 3600 = 7200 seconds) has zero buses running
    current_seconds = 2 * 3600
    geojson = sim.get_bus_positions_geojson(current_seconds)
    
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 0, "No buses should be running at 2:00 AM"
