import pytest
from pytest_httpx import HTTPXMock
from poc_stac_tokyo_taito.ckan_client import CKANClient

@pytest.mark.asyncio
async def test_fetch_all_datasets_success(httpx_mock: HTTPXMock):
    client = CKANClient()
    mock_response = {
        "success": True,
        "result": {
            "results": [
                {
                    "name": "t131067d0001",
                    "title": "台東区 子ども食堂一覧",
                    "resources": [
                        {"format": "CSV", "url": "https://example.com/child_shokudo.csv"}
                    ]
                }
            ]
        }
    }
    
    httpx_mock.add_response(
        url=f"{client.search_url}?fq=organization%3A{client.org_id}&rows=1000",
        json=mock_response
    )
    
    datasets = await client.fetch_all_datasets()
    assert len(datasets) == 1
    assert datasets[0]["name"] == "t131067d0001"
    assert datasets[0]["title"] == "台東区 子ども食堂一覧"

@pytest.mark.asyncio
async def test_fetch_all_datasets_failure(httpx_mock: HTTPXMock):
    client = CKANClient()
    httpx_mock.add_response(
        url=f"{client.search_url}?fq=organization%3A{client.org_id}&rows=1000",
        status_code=500
    )
    
    datasets = await client.fetch_all_datasets()
    assert datasets == []

def test_filter_facility_datasets():
    client = CKANClient()
    datasets = [
        {
            "name": "t131067d0001",
            "title": "台東区 子ども食堂一覧",
            "notes": "子ども食堂の場所です",
            "resources": [{"format": "CSV", "url": "https://example.com/1.csv"}]
        },
        {
            "name": "t131067d0002",
            "title": "台東区 統計情報（人口）",
            "notes": "統計データ",
            "resources": [{"format": "CSV", "url": "https://example.com/2.csv"}]
        },
        {
            "name": "t131067d0003",
            "title": "台東区 避難所一覧",
            "notes": "PDFの避難所です",
            "resources": [{"format": "PDF", "url": "https://example.com/3.pdf"}]
        }
    ]
    
    filtered = client.filter_facility_datasets(datasets)
    assert len(filtered) == 1
    assert filtered[0]["name"] == "t131067d0001"

def test_get_csv_resource():
    client = CKANClient()
    dataset = {
        "resources": [
            {"format": "PDF", "url": "https://example.com/1.pdf"},
            {"format": "CSV", "url": "https://example.com/1.csv"}
        ]
    }
    res = client.get_csv_resource(dataset)
    assert res is not None
    assert res["format"] == "CSV"
    assert res["url"] == "https://example.com/1.csv"
