import logging
import httpx
from typing import List, Dict, Any, Optional
from poc_stac_tokyo_taito.config import CKAN_SEARCH_URL, TAITO_ORG_ID, TARGET_DATASET_KEYWORDS

logger = logging.getLogger(__name__)

class CKANClient:
    def __init__(self, search_url: str = CKAN_SEARCH_URL, org_id: str = TAITO_ORG_ID):
        self.search_url = search_url
        self.org_id = org_id

    async def fetch_all_datasets(self) -> List[Dict[str, Any]]:
        """
        Fetch all datasets for the organization from the Tokyo Open Data CKAN API.
        """
        logger.info(f"Fetching datasets for organization {self.org_id} from {self.search_url}")
        
        # Request all rows to fetch everything in one go (there are ~187 datasets in Taito-ku)
        params = {
            "fq": f"organization:{self.org_id}",
            "rows": 1000
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(self.search_url, params=params)
                response.raise_for_status()
                data = response.json()
                if not data.get("success"):
                    logger.error(f"CKAN API returned success=False: {data}")
                    return []
                
                results = data.get("result", {}).get("results", [])
                logger.info(f"Successfully fetched {len(results)} datasets from CKAN.")
                return results
            except Exception as e:
                logger.error(f"Failed to fetch datasets from CKAN: {e}", exc_info=True)
                return []

    def filter_facility_datasets(self, datasets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter datasets to find facility datasets (CSV, containing target keywords in title/notes).
        """
        filtered = []
        for ds in datasets:
            title = ds.get("title", "")
            notes = ds.get("notes", "") or ""
            
            # Check if there is at least one CSV resource
            has_csv = False
            for resource in ds.get("resources", []):
                fmt = resource.get("format", "").upper()
                if "CSV" in fmt:
                    has_csv = True
                    break
            
            if not has_csv:
                continue

            # Check if title or notes matches our keywords
            match = False
            for kw in TARGET_DATASET_KEYWORDS:
                if kw in title or kw in notes:
                    match = True
                    break
            
            if match:
                filtered.append(ds)
                
        logger.info(f"Filtered {len(filtered)} facility datasets matching keywords out of {len(datasets)} total.")
        return filtered

    def get_csv_resource(self, dataset: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get the first CSV resource in the dataset.
        """
        for res in dataset.get("resources", []):
            fmt = res.get("format", "").upper()
            if "CSV" in fmt:
                return res
        return None
