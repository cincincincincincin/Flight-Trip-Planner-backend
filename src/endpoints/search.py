from fastapi import APIRouter, Query, HTTPException, Request
from typing import Optional, Dict, Any, List
import logging
from src.services.search_service import search_service
from src.cache import cache
from src.limiter import limiter
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])

TTL_SEARCH = settings.cache_ttl_search
TTL_EXPAND = settings.cache_ttl_expand
TTL_ENTITY = settings.cache_ttl_entity

# ================ MAIN SEARCH ENDPOINT (Sequential Phases) ================

@router.get("")
@limiter.limit(settings.rate_limit_search)
async def unified_search(
    request: Request,
    q: str = Query("", description="Search query (empty for all countries)"),
    offset: int = Query(0, ge=0, description="Sequential offset across all phases"),
    limit: int = Query(20, ge=1, le=50, description="Number of items to return"),
    lang: str = Query('en', description="Language for localized names (en/pl)")
):
    """
    Unified search endpoint with sequential phases:

    For empty query: Only phase 1 (countries), infinite scroll through all countries
    For non-empty query:
      Phase 1: Matching countries
      Phase 2: Countries with matching cities (when phase 1 exhausted)
      Phase 3: Full hierarchy with matching airports (when phase 2 exhausted)

    Uses prefix search first, falls back to contains only if ALL phases are empty.
    """
    try:
        logger.info(f"[ENDPOINT] GET /search called with q='{q}', offset={offset}, limit={limit}, lang={lang}")

        key = f"search:{q.strip().lower()}:{offset}:{limit}:{lang}"
        cached_val = await cache.get(key)
        if cached_val is not None:
            return cached_val

        # Determine search mode based on all phases
        search_mode = await search_service.determine_search_mode(q, lang)

        # Get results for the current offset phase
        result = await search_service.get_sequential_phase_results(
            query=q,
            offset=offset,
            limit=limit,
            mode=search_mode,
            lang=lang
        )

        # Check if we should try contains search when prefix returned nothing
        if (search_mode == "prefix" and
            len(result["data"]) == 0 and
            q.strip() != ""):

            # Try contains search
            logger.info(f"[ENDPOINT] Prefix search returned empty, trying contains")
            search_mode = "contains"
            result = await search_service.get_sequential_phase_results(
                query=q,
                offset=offset,
                limit=limit,
                mode=search_mode,
                lang=lang
            )

        # Determine if next phases are available
        has_phase2 = await search_service.has_phase2_results(q, search_mode, lang)
        has_phase3 = await search_service.has_phase3_results(q, search_mode, lang)

        # If current phase has no more data, but next phase is available, set has_more to true
        # This tells frontend to keep loading (which will trigger next phase)
        has_more = result["has_more"]
        if not has_more and result["next_phase_available"]:
            has_more = True

        # Exact IATA code match — included so the frontend doesn't need a separate request
        exact_match = None
        if len(q.strip()) == 3:
            exact_match = await search_service.get_airport_by_code(q.strip().upper(), lang)

        response = {
            "success": True,
            "query": q,
            "search_mode": search_mode,
            "phase": result["phase"],
            "offset": offset,
            "limit": limit,
            "data": result["data"],
            "has_more": has_more,
            "next_offset": offset + len(result["data"]),
            "phase_info": {
                "current": result["phase"],
                "has_phase2": has_phase2,
                "has_phase3": has_phase3,
                "total_in_current_phase": result.get("total_in_phase", 0),
                "next_phase_available": result.get("next_phase_available", False)
            },
            "exact_match": exact_match,
        }
        await cache.set(key, response, TTL_SEARCH)
        return response

    except Exception as e:
        logger.error(f"[ENDPOINT ERROR] /search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")

# ================ GET ITEM BY CODE ENDPOINTS ================

@router.get("/airport/{code}")
@limiter.limit(settings.rate_limit_airports)
async def get_airport_by_code(
    request: Request,
    code: str,
    lang: str = Query('en', description="Language for localized names (en/pl)")
):
    """Get airport by code with full details"""
    try:
        logger.info(f"[ENDPOINT] GET /search/airport/{code}")
        key = f"search:airport:{code.upper()}:{lang}"
        result = await cache.cached(key, TTL_ENTITY, lambda: search_service.get_airport_by_code(code, lang))
        if not result:
            raise HTTPException(status_code=404, detail=f"Airport {code} not found")
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ENDPOINT ERROR] /search/airport/{code}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting airport: {str(e)}")

@router.get("/city/{code}")
@limiter.limit(settings.rate_limit_airports)
async def get_city_by_code(
    request: Request,
    code: str,
    lang: str = Query('en', description="Language for localized names (en/pl)")
):
    """Get city by code with full details"""
    try:
        logger.info(f"[ENDPOINT] GET /search/city/{code}")
        key = f"search:city:{code.upper()}:{lang}"
        result = await cache.cached(key, TTL_ENTITY, lambda: search_service.get_city_by_code(code, lang))
        if not result:
            raise HTTPException(status_code=404, detail=f"City {code} not found")
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ENDPOINT ERROR] /search/city/{code}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting city: {str(e)}")

# ================ EXPAND ENDPOINTS (For UI expanding) ================

@router.get("/countries/{country_code}/cities")
@limiter.limit(settings.rate_limit_airports)
async def get_cities_in_country(
    request: Request,
    country_code: str,
    limit: int = Query(settings.search_cities_page_size, ge=1, le=200, description="Limit results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    lang: str = Query('en', description="Language for localized names (en/pl)")
):
    """
    Get ALL cities in a specific country (for expanding country in UI)
    This returns all cities, not just matching ones.
    """
    try:
        logger.info(f"[ENDPOINT] GET /search/countries/{country_code}/cities called with "
                   f"limit={limit}, offset={offset}, lang={lang}")

        key = f"country_cities:{country_code.upper()}:{offset}:{limit}:{lang}"
        cached_val = await cache.get(key)
        if cached_val is not None:
            return cached_val

        # First get country info
        country = await search_service.get_country_by_code(country_code, lang)
        if not country:
            raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

        # Get all cities in the country
        cities = await search_service.get_all_cities_in_country(
            country_code, limit, offset, lang
        )

        total = await search_service.get_all_cities_in_country_count(country_code)

        response = {
            "success": True,
            "country": country,
            "data": cities,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
                "has_more": offset + len(cities) < total
            }
        }
        await cache.set(key, response, TTL_EXPAND)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ENDPOINT ERROR] /search/countries/{country_code}/cities: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting cities: {str(e)}")

@router.get("/cities/{city_code}/airports")
@limiter.limit(settings.rate_limit_airports)
async def get_airports_in_city(
    request: Request,
    city_code: str,
    limit: int = Query(settings.search_airports_page_size, ge=1, le=500, description="Limit results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    lang: str = Query('en', description="Language for localized names (en/pl)")
):
    """
    Get ALL airports in a specific city (for expanding city in UI)
    This returns all airports, not just matching ones.
    """
    try:
        logger.info(f"[ENDPOINT] GET /search/cities/{city_code}/airports called with "
                   f"limit={limit}, offset={offset}, lang={lang}")

        key = f"city_airports:{city_code.upper()}:{offset}:{limit}:{lang}"
        cached_val = await cache.get(key)
        if cached_val is not None:
            return cached_val

        # First get city info
        city = await search_service.get_city_by_code(city_code, lang)
        if not city:
            raise HTTPException(status_code=404, detail=f"City {city_code} not found")

        # Get all airports in the city
        airports = await search_service.get_all_airports_in_city(
            city_code, limit, offset, lang
        )

        total = await search_service.get_all_airports_in_city_count(city_code)

        response = {
            "success": True,
            "city": city,
            "data": airports,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
                "has_more": offset + len(airports) < total
            }
        }
        await cache.set(key, response, TTL_EXPAND)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ENDPOINT ERROR] /search/cities/{city_code}/airports: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting airports: {str(e)}")

@router.get("/country/{code}/center")
@limiter.limit(settings.rate_limit_airports)
async def get_country_center(request: Request, code: str):
    """
    Zwraca centroid kraju (średnia współrzędnych miast/lotnisk) oraz
    rekomendowany zoom na podstawie liczby lotnisk w kraju.
    """
    try:
        logger.info(f"[ENDPOINT] GET /search/country/{code}/center")

        key = f"search:country_center:{code.upper()}"
        cached_val = await cache.get(key)
        if cached_val is not None:
            return cached_val

        country = await search_service.get_country_by_code(code)
        if not country:
            raise HTTPException(status_code=404, detail=f"Country {code} not found")

        result = await search_service.get_country_center(code)
        if not result:
            raise HTTPException(status_code=404, detail=f"Cannot determine center for country {code}")

        response = {
            "success": True,
            "country_code": code,
            "country_name": country.get('name'),
            "lon": result["lon"],
            "lat": result["lat"],
            "airport_count": result["airport_count"],
            "recommended_zoom": result["recommended_zoom"]
        }
        await cache.set(key, response, TTL_ENTITY)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ENDPOINT ERROR] /search/country/{code}/center: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting country center: {str(e)}")