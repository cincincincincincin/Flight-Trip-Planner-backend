import asyncio
import logging
from fastapi import APIRouter, Query, Request, HTTPException
from src.services.airport_service import airport_service
from src.database import db
from src.cache import cache
from src.limiter import limiter
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["init"])

TTL = settings.cache_ttl_geojson


async def _fetch_country_centers() -> dict:
    async with db.get_connection() as conn:
        rows = await conn.fetch("""
            SELECT code, center_lon, center_lat, center_zoom
            FROM countries
            WHERE center_lon IS NOT NULL
              AND center_lat IS NOT NULL
        """)
    return {
        row["code"]: {
            "lon": row["center_lon"],
            "lat": row["center_lat"],
            "zoom": row["center_zoom"],
        }
        for row in rows
    }


async def _fetch_init(lang: str) -> dict:
    geojson, country_centers = await asyncio.gather(
        cache.cached(
            f"geojson:airports:None:{lang}",
            TTL,
            lambda: airport_service.get_airports_as_geojson(lang=lang),
        ),
        cache.cached(
            "countries:centers",
            TTL,
            _fetch_country_centers,
        ),
    )
    return {"geojson": geojson, "country_centers": country_centers}


@router.get("/init")
@limiter.limit(settings.rate_limit_airports)
async def get_init_data(
    request: Request,
    lang: str = Query("en", description="Language for localized names (en/pl)"),
):
    """Return airports GeoJSON and country centers in a single request."""
    try:
        lang = lang if lang in ("en", "pl") else "en"
        return await _fetch_init(lang)
    except Exception as e:
        logger.error(f"[ENDPOINT ERROR] /init: {e}")
        raise HTTPException(status_code=500, detail=f"Error loading init data: {str(e)}")
