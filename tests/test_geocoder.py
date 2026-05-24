import pytest
import tempfile
from pathlib import Path
from pytest_httpx import HTTPXMock
from poc_stac_tokyo_taito.geocoder import Geocoder
from poc_stac_tokyo_taito.config import TAITO_CENTER_LAT, TAITO_CENTER_LON

def test_clean_address():
    geocoder = Geocoder(cache_path=Path("/tmp/nonexistent_cache.json"), delay_seconds=0.0)
    assert geocoder.clean_address(" 東京都台東区東上野4-5-6  ") == "東京都台東区東上野4-5-6"
    assert geocoder.clean_address("") == ""

def test_get_fallback_address():
    geocoder = Geocoder(cache_path=Path("/tmp/nonexistent_cache.json"), delay_seconds=0.0)
    
    # Check chome extraction
    assert geocoder.get_fallback_address("東京都台東区東上野4-5-6") == "東京都台東区東上野4"
    assert geocoder.get_fallback_address("東京都台東区西浅草3丁目1-2") == "東京都台東区西浅草3丁目"
    
    # Check general town extraction
    assert geocoder.get_fallback_address("東京都台東区浅草") is None
    assert geocoder.get_fallback_address("東京都台東区根岸5") == "東京都台東区根岸"

@pytest.mark.asyncio
async def test_geocode_cache_hit(tmp_path):
    cache_file = tmp_path / "cache.json"
    # Pre-populate cache
    geocoder = Geocoder(cache_path=cache_file, delay_seconds=0.0)
    geocoder.cache["東京都台東区東上野4-5-6"] = (139.78, 35.71)
    geocoder._save_cache()
    
    # Create new instance to test loading from cache file
    geocoder2 = Geocoder(cache_path=cache_file, delay_seconds=0.0)
    lon, lat, is_fallback = await geocoder2.geocode("東京都台東区東上野4-5-6")
    
    assert lon == 139.78
    assert lat == 35.71
    assert not is_fallback

@pytest.mark.asyncio
async def test_geocode_api_call_success(tmp_path, httpx_mock: HTTPXMock):
    cache_file = tmp_path / "cache.json"
    geocoder = Geocoder(cache_path=cache_file, delay_seconds=0.0)
    
    mock_nominatim_response = [
        {
            "lon": "139.7842",
            "lat": "35.7151"
        }
    ]
    
    # Add response for the search query
    httpx_mock.add_response(
        url=f"{geocoder.nominatim_url}/search?q=東京都台東区東上野4-5-6&format=json&limit=1&viewbox=139.75%2C35.75%2C139.83%2C35.68&bounded=1",
        json=mock_nominatim_response
    )
    
    lon, lat, is_fallback = await geocoder.geocode("東京都台東区東上野4-5-6")
    assert lon == 139.7842
    assert lat == 35.7151
    assert not is_fallback
    
    # Verify it was saved to the cache
    assert "東京都台東区東上野4-5-6" in geocoder.cache
    assert geocoder.cache["東京都台東区東上野4-5-6"] == (139.7842, 35.7151)

@pytest.mark.asyncio
async def test_geocode_api_call_fallback(tmp_path, httpx_mock: HTTPXMock):
    cache_file = tmp_path / "cache.json"
    geocoder = Geocoder(cache_path=cache_file, delay_seconds=0.0)
    
    # First search for full address returns empty list
    httpx_mock.add_response(
        url=f"{geocoder.nominatim_url}/search?q=東京都台東区東上野4-5-6&format=json&limit=1&viewbox=139.75%2C35.75%2C139.83%2C35.68&bounded=1",
        json=[]
    )
    
    # Fallback address search returns coordinates
    mock_fallback_response = [
        {
            "lon": "139.7800",
            "lat": "35.7100"
        }
    ]
    httpx_mock.add_response(
        url=f"{geocoder.nominatim_url}/search?q=東京都台東区東上野4&format=json&limit=1&viewbox=139.75%2C35.75%2C139.83%2C35.68&bounded=1",
        json=mock_fallback_response
    )
    
    lon, lat, is_fallback = await geocoder.geocode("東京都台東区東上野4-5-6")
    assert lon == 139.7800
    assert lat == 35.7100
    assert is_fallback
    
    assert "東京都台東区東上野4" in geocoder.cache
    assert "東京都台東区東上野4-5-6" in geocoder.cache

@pytest.mark.asyncio
async def test_geocode_completely_fails(tmp_path, httpx_mock: HTTPXMock):
    cache_file = tmp_path / "cache.json"
    geocoder = Geocoder(cache_path=cache_file, delay_seconds=0.0)
    
    # Both queries return empty
    httpx_mock.add_response(
        url=f"{geocoder.nominatim_url}/search?q=東京都台東区東上野4-5-6&format=json&limit=1&viewbox=139.75%2C35.75%2C139.83%2C35.68&bounded=1",
        json=[]
    )
    httpx_mock.add_response(
        url=f"{geocoder.nominatim_url}/search?q=東京都台東区東上野4&format=json&limit=1&viewbox=139.75%2C35.75%2C139.83%2C35.68&bounded=1",
        json=[]
    )
    
    lon, lat, is_fallback = await geocoder.geocode("東京都台東区東上野4-5-6")
    assert lon == TAITO_CENTER_LON
    assert lat == TAITO_CENTER_LAT
    assert is_fallback
