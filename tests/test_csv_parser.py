import pytest
from poc_stac_tokyo_taito.csv_parser import CSVParser

def test_detect_and_decode_utf8_sig():
    content = "\ufeff名称,所在地_連結表記,緯度,経度\nテスト施設,台東区東上野4-5-6,35.1,139.1\n".encode("utf-8")
    decoded = CSVParser.detect_and_decode(content)
    assert "名称" in decoded
    assert "テスト施設" in decoded

def test_detect_and_decode_cp932():
    content = "名称,所在地_連結表記,緯度,経度\nテスト施設,台東区東上野4-5-6,35.1,139.1\n".encode("cp932")
    decoded = CSVParser.detect_and_decode(content)
    assert "名称" in decoded
    assert "テスト施設" in decoded

def test_parse_csv_content():
    csv_text = "名称,所在地_連結表記,緯度,経度\nテスト施設,台東区東上野4-5-6,35.1,139.1\n"
    parser = CSVParser()
    records = parser.parse_csv_content(csv_text)
    
    assert len(records) == 1
    assert records[0]["名称"] == "テスト施設"
    assert records[0]["所在地_連結表記"] == "台東区東上野4-5-6"
    assert records[0]["緯度"] == "35.1"
    assert records[0]["経度"] == "139.1"

def test_extract_address_and_coordinates_full():
    parser = CSVParser()
    
    # Case 1: Coordinates present in record
    record = {
        "名称": "テスト施設",
        "所在地_連結表記": "台東区東上野4-5-6",
        "緯度": "35.12345",
        "経度": "139.54321"
    }
    addr, lon, lat = parser.extract_address_and_coordinates(record)
    assert addr == "東京都台東区東上野4-5-6"
    assert lon == 139.54321
    assert lat == 35.12345

    # Case 2: No coordinates, structured address
    record_no_coords = {
        "名称": "テスト施設2",
        "所在地_都道府県": "東京都",
        "所在地_市区町村": "台東区",
        "所在地_町字": "西浅草3丁目",
        "所在地_番地以下": "1-2"
    }
    addr, lon, lat = parser.extract_address_and_coordinates(record_no_coords)
    assert addr == "東京都台東区西浅草3丁目1-2"
    assert lon is None
    assert lat is None
