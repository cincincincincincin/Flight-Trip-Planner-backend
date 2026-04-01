from fastapi import APIRouter, HTTPException, Request
from src.database import db
from src.cache import cache
from src.limiter import limiter
from src.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/countries", tags=["countries"])

TTL = settings.cache_ttl_geojson


@router.get("/centers")
@limiter.limit(settings.rate_limit_airports)
async def get_country_centers(request: Request):
    """
    Returns precomputed centroids and recommended zoom levels for all countries.
    Response: { "PL": { "lon": 19.5, "lat": 52.0, "zoom": 4.5 }, ... }
    """
    try:
        key = "countries:centers"
        cached = await cache.get(key)
        if cached is not None:
            return cached

        async with db.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT code, center_lon, center_lat, center_zoom
                FROM countries
                WHERE center_lon IS NOT NULL
                  AND center_lat IS NOT NULL
            """)

        result = {
            row["code"]: {
                "lon": row["center_lon"],
                "lat": row["center_lat"],
                "zoom": row["center_zoom"],
            }
            for row in rows
        }
        await cache.set(key, result, TTL)
        return result

    except Exception as e:
        logger.error(f"[ENDPOINT ERROR] /countries/centers: {e}")
        raise HTTPException(status_code=500, detail="Error loading country centers")
