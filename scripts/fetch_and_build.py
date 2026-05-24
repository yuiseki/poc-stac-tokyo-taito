import asyncio
import logging
import sys
from pathlib import Path

# Add src to python path so we can import our package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from poc_stac_tokyo_taito.ckan_client import CKANClient
from poc_stac_tokyo_taito.csv_parser import CSVParser
from poc_stac_tokyo_taito.geocoder import Geocoder
from poc_stac_tokyo_taito.geojson_converter import GeoJSONConverter
from poc_stac_tokyo_taito.stac_builder import STACBuilder

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("fetch_and_build_pipeline")

async def main():
    logger.info("Starting Taito-ku STAC pipeline...")
    
    # 1. Initialize Components
    ckan_client = CKANClient()
    csv_parser = CSVParser()
    geocoder = Geocoder()
    geojson_converter = GeoJSONConverter(geocoder=geocoder)
    stac_builder = STACBuilder()
    
    # 2. Fetch all datasets from CKAN
    logger.info("Fetching datasets from CKAN...")
    all_datasets = await ckan_client.fetch_all_datasets()
    if not all_datasets:
        logger.error("No datasets fetched. Exiting.")
        return
        
    # 3. Filter for Phase 1 facility datasets
    logger.info("Filtering facility datasets...")
    target_datasets = ckan_client.filter_facility_datasets(all_datasets)
    logger.info(f"Found {len(target_datasets)} facility datasets to process.")
    
    stac_items = []
    active_collection_ids = set()
    
    # 4. Process each dataset
    for idx, ds in enumerate(target_datasets, 1):
        ds_name = ds.get("name")
        ds_title = ds.get("title")
        collection_id = stac_builder.get_collection_id(ds)
        
        logger.info(f"[{idx}/{len(target_datasets)}] Processing dataset: '{ds_title}' (ID: {ds_name}) in Collection '{collection_id}'")
        
        csv_res = ckan_client.get_csv_resource(ds)
        if not csv_res:
            logger.warning(f"No CSV resource found for dataset '{ds_title}'. Skipping.")
            continue
            
        csv_url = csv_res.get("url")
        
        # Download and Parse CSV
        records = await csv_parser.download_and_parse(csv_url)
        if not records:
            logger.warning(f"No records found or parsed for CSV: {csv_url}. Skipping.")
            continue
            
        # Convert to GeoJSON FeatureCollection
        try:
            geojson = await geojson_converter.records_to_geojson(records)
            
            # Save GeoJSON file locally to docs/data/
            geojson_file_path = geojson_converter.save_geojson(ds_name, geojson)
            logger.info(f"Successfully generated and saved GeoJSON for '{ds_title}' ({len(records)} features)")
            
            # Build STAC Item
            # We assume relative links or absolute links in local dev
            geojson_relative_url = f"/docs/data/{ds_name}.geojson"
            
            stac_item = stac_builder.build_item(
                dataset=ds,
                geojson=geojson,
                geojson_url=geojson_relative_url,
                csv_url=csv_url
            )
            
            stac_items.append(stac_item)
            active_collection_ids.add(collection_id)
            
        except Exception as e:
            logger.error(f"Error converting and building STAC Item for '{ds_title}': {e}", exc_info=True)
            continue
            
    # 5. Build and Save active STAC Collections
    logger.info(f"Building {len(active_collection_ids)} active collections...")
    stac_collections = []
    for col_id in active_collection_ids:
        stac_col = stac_builder.build_collection(col_id)
        stac_collections.append(stac_col)
        
    # 6. Persist STAC metadata files
    stac_builder.save_stac_data(stac_collections, stac_items)
    logger.info("Taito-ku STAC pipeline completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
