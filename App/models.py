# models.py - Corrected
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# Property Models
class PropertyLocation(BaseModel):
    address: str
    city: str
    state: str
    zip_code: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    neighborhood: Optional[str] = None

class PropertyDetails(BaseModel):
    bedrooms: int
    bathrooms: float
    square_feet: Optional[int] = None
    lot_size: Optional[float] = None
    year_built: Optional[int] = None
    property_type: str  # house, apartment, condo, etc.
    parking: Optional[str] = None
    amenities: Optional[List[str]] = []

class Property(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    price: float
    location: PropertyLocation
    details: PropertyDetails
    images: Optional[List[str]] = []
    listing_date: Optional[datetime] = None
    status: str = "active"  # active, sold, pending
    agent_contact: Optional[str] = None

# Search Models
class PropertySearchFilters(BaseModel):
    location: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    property_type: Optional[str] = None
    min_sqft: Optional[int] = None
    max_sqft: Optional[int] = None
    amenities: Optional[List[str]] = None

class PropertySearchRequest(BaseModel):
    query: Optional[str] = None
    filters: Optional[PropertySearchFilters] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=100)
    sort_by: Optional[str] = "price"  # price, date, relevance
    sort_order: Optional[str] = "asc"  # asc, desc
    # Individual filter fields for backward compatibility
    location: Optional[str] = None
    property_type: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_bedrooms: Optional[int] = None
    max_bedrooms: Optional[int] = None
    min_bathrooms: Optional[int] = None
    max_bathrooms: Optional[int] = None
    min_sqft: Optional[int] = None
    max_sqft: Optional[int] = None
    amenities: Optional[List[str]] = None

class PropertySearchResponse(BaseModel):
    properties: List[Property]
    total: int
    page: int
    limit: int
    total_pages: int

# Location Trends Models
class LocationTrendData(BaseModel):
    date: str
    average_price: float
    median_price: float
    properties_sold: int
    price_per_sqft: Optional[float] = None

class LocationTrends(BaseModel):
    location: str
    data: List[LocationTrendData]
    summary: Dict[str, Any]

class LocationTrendsRequest(BaseModel):
    location: str
    time_period: str = "1year"  # 1month, 6months, 1year, 2years
    property_type: Optional[str] = None

# Chat Models
class ChatMessage(BaseModel):
    message: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    response: str
    properties: Optional[List[Property]] = None
    suggestions: Optional[List[str]] = None
    session_id: Optional[str] = None
    requires_action: Optional[bool] = False
    action_type: Optional[str] = None

# Response Models
class APIResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None
    error: Optional[str] = None