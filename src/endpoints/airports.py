from fastapi import APIRouter, Query, HTTPException, Request
from typing import Optional
from src.services.airport_service import airport_service
from src.models.airport import AirportsResponse, AirportResponse
from src.cache import cache
from src.limiter import limiter
from src.config import settings

router = APIRouter(prefix="/airports", tags=["airports"])

TTL_GEOJSON = settings.cache_ttl_geojson
TTL_ENTITY = settings.cache_ttl_entity

@router.get("/", response_model=AirportsResponse)
@limiter.limit(settings.rate_limit_airports)
async def get_airports(
    request: Request,
    country_code: Optional[str] = Query(None, description="Filter by country code"),
    city_code: Optional[str] = Query(None, description="Filter by city code"),
    limit: Optional[int] = Query(None, description="Limit results (None = no limit)"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """Get all airports with optional filters"""
    try:
        airports = await airport_service.get_all_airports(
            country_code=country_code,
            city_code=city_code,
            limit=limit,
            offset=offset
        )

        count = await airport_service.get_airports_count(
            country_code=country_code
        )

        return AirportsResponse(
            data=airports,
            count=count
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/geojson")
@limiter.limit(settings.rate_limit_airports)
async def get_airports_geojson(
    request: Request,
    limit: Optional[int] = Query(None, description="Limit results (None = no limit)"),
    lang: str = Query('en', description="Language for localized names (en/pl)")
):
    """Get airports as GeoJSON for mapping"""
    try:
        key = f"geojson:airports:{limit}:{lang}"
        return await cache.cached(key, TTL_GEOJSON,
            lambda: airport_service.get_airports_as_geojson(limit=limit, lang=lang))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading airports: {str(e)}")

@router.get("/by-country/{country_code}", response_model=AirportsResponse)
@limiter.limit(settings.rate_limit_airports)
async def get_airports_by_country(
    request: Request,
    country_code: str,
    lang: str = Query('en', description="Language for localized names (en/pl)")
):
    """Get all airports for a country with timezone data (single cached query)"""
    key = f"airports:country:{country_code.upper()}:{lang}"
    airports = await cache.cached(key, TTL_ENTITY,
        lambda: airport_service.get_all_airports(country_code=country_code.upper(), lang=lang))
    if airports is None:
        airports = []
    return AirportsResponse(data=airports, count=len(airports))

@router.get("/{code}", response_model=AirportResponse)
@limiter.limit(settings.rate_limit_airports)
async def get_airport(request: Request, code: str):
    """Get airport by IATA code"""
    key = f"airport:{code.upper()}"
    airport = await cache.cached(key, TTL_ENTITY, lambda: airport_service.get_airport_by_code(code))
    if not airport:
        raise HTTPException(status_code=404, detail="Airport not found")
    return AirportResponse(data=airport)
