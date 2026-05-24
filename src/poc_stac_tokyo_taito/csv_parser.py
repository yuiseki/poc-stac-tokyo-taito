import csv
import io
import logging
from typing import List, Dict, Any, Tuple, Optional
import httpx

logger = logging.getLogger(__name__)

class CSVParser:
    @staticmethod
    def detect_and_decode(content: bytes) -> str:
        """
        Attempt to decode bytes using different encodings common in Japanese CSVs.
        """
        encodings = ["utf-8-sig", "utf-8", "cp932", "shift_jis"]
        for enc in encodings:
            try:
                decoded = content.decode(enc)
                # Quick check if it decoded reasonably (no replacement characters if we can avoid them)
                if "\ufffd" not in decoded:
                    logger.debug(f"Successfully decoded CSV using encoding: {enc}")
                    return decoded
            except UnicodeDecodeError:
                continue
        
        # Fallback to the first one that doesn't crash, even with some replacement chars
        for enc in encodings:
            try:
                return content.decode(enc, errors="replace")
            except Exception:
                continue
                
        return content.decode("utf-8", errors="replace")

    async def download_and_parse(self, url: str) -> List[Dict[str, Any]]:
        """
        Download CSV from the given URL, decode it, and parse into list of dicts.
        """
        logger.info(f"Downloading CSV from: {url}")
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content
                
                csv_text = self.detect_and_decode(content)
                return self.parse_csv_content(csv_text)
            except Exception as e:
                logger.error(f"Failed to download and parse CSV from {url}: {e}", exc_info=True)
                return []

    def parse_csv_content(self, csv_text: str) -> List[Dict[str, Any]]:
        """
        Parse CSV text into a list of dictionaries.
        """
        # Clean potential empty lines and split
        f = io.StringIO(csv_text.strip())
        reader = csv.DictReader(f)
        
        records = []
        for row in reader:
            # Clean up keys and values (strip whitespaces)
            cleaned_row = {
                (k.strip() if k else ""): (v.strip() if v else "")
                for k, v in row.items()
            }
            # Remove empty key if any
            if "" in cleaned_row:
                del cleaned_row[""]
            records.append(cleaned_row)
            
        logger.info(f"Parsed {len(records)} records from CSV content.")
        return records

    def extract_address_and_coordinates(self, record: Dict[str, Any]) -> Tuple[Optional[str], Optional[float], Optional[float]]:
        """
        Extract address and coordinates (if already present) from a CSV record.
        Returns: (address, longitude, latitude)
        """
        # 1. Coordinate extraction
        lon = None
        lat = None
        
        lon_keys = ["経度", "longitude", "lon", "lng"]
        lat_keys = ["緯度", "latitude", "lat"]
        
        for k, v in record.items():
            k_lower = k.lower()
            if any(lk in k_lower for lk in lon_keys):
                try:
                    if v and v != "0" and v != "0.0":
                        lon = float(v)
                except ValueError:
                    pass
            if any(lk in k_lower for lk in lat_keys):
                try:
                    if v and v != "0" and v != "0.0":
                        lat = float(v)
                except ValueError:
                    pass

        # 2. Address extraction
        address = None
        
        # Priority 1: Direct unified address fields
        addr_keys = [
            "所在地_連結表記",
            "住所",
            "所在地",
            "所在地_住所",
            "場所",
            "所在地（連結表記）",
        ]
        for ak in addr_keys:
            if ak in record and record[ak]:
                address = record[ak]
                break
                
        # Priority 2: Structured parts of address
        if not address:
            pref = record.get("所在地_都道府県", "")
            city = record.get("所在地_市区町村", "")
            town = record.get("所在地_町字", "")
            remainder = record.get("所在地_番地以下", "")
            
            if city or town:
                address = f"{pref}{city}{town}{remainder}".strip()

        # Ensure "東京都台東区" is prefixed if the address is local and does not contain it
        if address:
            # Clean up common garbage values
            address = address.replace("\u3000", " ").strip()
            if address and not address.startswith("東京都") and "台東区" not in address:
                address = f"東京都台東区{address}"
            elif address and address.startswith("台東区"):
                address = f"東京都{address}"

        return address, lon, lat
