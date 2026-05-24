from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class StacLink(BaseModel):
    rel: str
    href: str
    type: Optional[str] = None
    title: Optional[str] = None

class StacProvider(BaseModel):
    name: str
    description: Optional[str] = None
    roles: List[str]
    url: Optional[str] = None

class StacSpatialExtent(BaseModel):
    bbox: List[List[float]]

class StacTemporalExtent(BaseModel):
    interval: List[List[Optional[str]]]

class StacExtent(BaseModel):
    spatial: StacSpatialExtent
    temporal: StacTemporalExtent

class StacCollection(BaseModel):
    type: str = "Collection"
    stac_version: str = "1.0.0"
    id: str
    title: str
    description: str
    license: str
    extent: StacExtent
    providers: List[StacProvider]
    links: List[StacLink]

class StacItem(BaseModel):
    type: str = "Feature"
    stac_version: str = "1.0.0"
    id: str
    collection: str
    geometry: Dict[str, Any]
    bbox: List[float]
    properties: Dict[str, Any]
    assets: Dict[str, Any]
    links: List[StacLink]

class StacCatalog(BaseModel):
    type: str = "Catalog"
    stac_version: str = "1.0.0"
    id: str = "poc-stac-tokyo-taito"
    title: str = "台東区オープンデータ STAC API"
    description: str = "台東区のオープンデータ (CSV) を GeoJSON に変換し、STAC API エンドポイントとして提供する POC プロジェクト。"
    links: List[StacLink]

class StacSearchRequest(BaseModel):
    bbox: Optional[List[float]] = None
    datetime: Optional[str] = None
    collections: Optional[List[str]] = None
    ids: Optional[List[str]] = None
    limit: Optional[int] = Field(default=10, ge=1, le=1000)
    token: Optional[str] = None
