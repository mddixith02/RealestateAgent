from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import json
import asyncio
from typing import Optional, List
from app.config import settings
from app.models import (
    PropertySearchRequest, PropertySearchResponse, PropertySearchFilters,
    ChatMessage, ChatResponse, LocationTrendsRequest,
    APIResponse, Property
)
from app.search import search_engine
from app.agent import real_estate_agent

# Initialize FastAPI app
app = FastAPI(
    title="Agentic Real Estate API",
    description="AI-powered real estate search and chat API",
    version="1.0.0",
    debug=settings.DEBUG
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    try:
        search_engine.create_index()
        print("✅ OpenSearch index created/verified")
    except Exception as e:
        print(f"❌ Error initializing search engine: {e}")

@app.get("/")
async def root():
    return {"message": "Agentic Real Estate API is running!", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    try:
        info = search_engine.client.info()
        return {
            "status": "healthy",
            "opensearch": "connected",
            "version": info.get("version", {}).get("number", "unknown")
        }
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})

@app.post("/api/properties/search", response_model=PropertySearchResponse)
async def search_properties(request: PropertySearchRequest):
    try:
        results = search_engine.search_properties(request)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")

@app.get("/api/properties/{property_id}", response_model=Property)
async def get_property(property_id: str):
    try:
        property_data = search_engine.get_property_by_id(property_id)
        if not property_data:
            raise HTTPException(status_code=404, detail="Property not found")
        return property_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving property: {str(e)}")

@app.post("/api/chat", response_model=ChatResponse)
async def chat_with_agent(message: ChatMessage):
    try:
        response = await real_estate_agent.process_message(
            message=message.message,
            context=message.context
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

@app.get("/api/chat/history/{session_id}")
async def get_chat_history(session_id: str, limit: int = 50):
    return {
        "session_id": session_id, 
        "messages": [],
        "message": "Chat history feature not yet implemented"
    }

@app.post("/api/trends/location")
async def get_location_trends(request: LocationTrendsRequest):
    try:
        trends = search_engine.get_location_trends(
            location=request.location,
            property_type=request.property_type,
            time_period=request.time_period
        )
        return {
            "location": request.location,
            "property_type": request.property_type,
            "time_period": request.time_period,
            "trends": trends
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving trends: {str(e)}")

@app.get("/api/locations/suggestions")
async def get_location_suggestions(query: str, limit: int = 10):
    try:
        suggestions = search_engine.get_location_suggestions(query, limit)
        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving suggestions: {str(e)}")

@app.post("/api/properties", response_model=APIResponse)
async def add_property(property_data: Property, background_tasks: BackgroundTasks):
    try:
        property_dict = property_data.dict()
        result = search_engine.add_property(property_dict)
        background_tasks.add_task(update_related_indexes, property_data.location.city)
        return APIResponse(
            success=True,
            message="Property added successfully",
            data={"property_id": result.get("_id", property_data.id)}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding property: {str(e)}")

@app.put("/api/properties/{property_id}", response_model=APIResponse)
async def update_property(property_id: str, property_data: Property):
    try:
        property_dict = property_data.dict()
        result = search_engine.update_property(property_id, property_dict)
        if not result:
            raise HTTPException(status_code=404, detail="Property not found")
        return APIResponse(
            success=True,
            message="Property updated successfully",
            data={"property_id": property_id}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating property: {str(e)}")

@app.delete("/api/properties/{property_id}", response_model=APIResponse)
async def delete_property(property_id: str):
    try:
        result = search_engine.delete_property(property_id)
        if not result:
            raise HTTPException(status_code=404, detail="Property not found")
        return APIResponse(
            success=True,
            message="Property deleted successfully",
            data={"property_id": property_id}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting property: {str(e)}")

@app.post("/api/users/{user_id}/favorites/{property_id}")
async def add_to_favorites(user_id: str, property_id: str):
    try:
        property_data = search_engine.get_property_by_id(property_id)
        if not property_data:
            raise HTTPException(status_code=404, detail="Property not found")
        return APIResponse(
            success=True,
            message="Property added to favorites",
            data={"user_id": user_id, "property_id": property_id}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding to favorites: {str(e)}")

@app.delete("/api/users/{user_id}/favorites/{property_id}")
async def remove_from_favorites(user_id: str, property_id: str):
    try:
        return APIResponse(
            success=True,
            message="Property removed from favorites",
            data={"user_id": user_id, "property_id": property_id}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error removing from favorites: {str(e)}")

@app.get("/api/users/{user_id}/favorites")
async def get_user_favorites(user_id: str):
    return {
        "user_id": user_id, 
        "favorites": [],
        "message": "User favorites feature not yet implemented"
    }

@app.get("/api/analytics/property-stats")
async def get_property_stats(location: Optional[str] = None, property_type: Optional[str] = None):
    try:
        stats = search_engine.get_property_stats(location, property_type)
        return {
            "location": location,
            "property_type": property_type,
            "statistics": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving statistics: {str(e)}")

@app.get("/api/properties/search")
async def search_properties_get(
    location: Optional[str] = None,
    property_type: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    bedrooms: Optional[int] = None,
    bathrooms: Optional[int] = None,
    min_sqft: Optional[int] = None,
    max_sqft: Optional[int] = None,
    page: int = 1,
    limit: int = 10,
    sort_by: str = "price",
    sort_order: str = "asc"
):
    try:
        filters = PropertySearchFilters(
            location=location,
            min_price=min_price,
            max_price=max_price,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            property_type=property_type,
            min_sqft=min_sqft,
            max_sqft=max_sqft
        )
        search_request = PropertySearchRequest(
            filters=filters,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order
        )
        results = search_engine.search_properties(search_request)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")

@app.post("/api/properties/bulk", response_model=APIResponse)
async def bulk_add_properties(properties: List[Property], background_tasks: BackgroundTasks):
    try:
        property_dicts = [prop.dict() for prop in properties]
        search_engine.bulk_index_properties(property_dicts)
        unique_locations = list(set([prop.location.city for prop in properties]))
        for location in unique_locations:
            background_tasks.add_task(update_related_indexes, location)
        return APIResponse(
            success=True,
            message=f"Successfully added {len(properties)} properties",
            data={"count": len(properties)}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error bulk adding properties: {str(e)}")

@app.post("/api/recommendations")
async def get_property_recommendations(preferences: dict):
    try:
        filters = PropertySearchFilters(
            location=preferences.get('location'),
            min_price=preferences.get('min_price'),
            max_price=preferences.get('max_price'),
            bedrooms=preferences.get('bedrooms'),
            bathrooms=preferences.get('bathrooms'),
            property_type=preferences.get('property_type')
        )
        search_request = PropertySearchRequest(filters=filters, limit=20)
        search_results = search_engine.search_properties(search_request)

        # Corrected: use asyncio.to_thread to avoid blocking
        recommendations = await asyncio.to_thread(
            real_estate_agent.get_property_recommendations,
            user_preferences=preferences,
            available_properties=search_results.properties
        )

        return {
            "preferences": preferences,
            "recommendations": recommendations,
            "properties": search_results.properties[:10]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")

async def update_related_indexes(location: str):
    try:
        search_engine.update_location_trends(location)
        search_engine.update_market_stats(location)
        print(f"✅ Updated indexes for location: {location}")
    except Exception as e:
        print(f"❌ Error updating indexes for {location}: {e}")

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"error": "Resource not found", "detail": str(exc.detail) if hasattr(exc, 'detail') else "Not found"})

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": "An unexpected error occurred"})

@app.exception_handler(422)
async def validation_error_handler(request, exc):
    return JSONResponse(status_code=422, content={"error": "Validation error", "detail": exc.errors() if hasattr(exc, 'errors') else str(exc)})

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=settings.DEBUG, log_level="info")