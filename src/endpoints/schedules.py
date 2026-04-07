import json
import logging
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from src.services.schedule_service import schedule_service
from src.limiter import limiter
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedules", tags=["schedules"])

@router.get("/{airport_code}")
@limiter.limit(settings.rate_limit_flights)
async def get_airport_schedule(
    request: Request,
    airport_code: str = Path(..., description="IATA airport code (e.g., 'WAW')"),
    from_local_datetime: str = Query(..., description="Start of window in local airport time (YYYY-MM-DDTHH:MM:SS)."),
    to_local_datetime: str = Query(..., description="End of window in local airport time (YYYY-MM-DDTHH:MM:SS)."),
    limit: int = Query(200, ge=1, le=2000, description="Max results"),
    force_refresh: bool = Query(False, description="Force refresh from API")
):
    """
    Zwraca strumień lotów dla wybranego lotniska w formacie NDJSON.
    Logika ta pozwala na płynne renderowanie listy na froncie.
    """
    try:
        try:
            parsed_from_dt = datetime.fromisoformat(from_local_datetime)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid from_local_datetime: {from_local_datetime}")

        try:
            parsed_to_dt = datetime.fromisoformat(to_local_datetime)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid to_local_datetime: {to_local_datetime}")

        async def response_generator():
            try:
                # Wykorzystujemy asynchroniczny generator rozkładu
                async for batch in schedule_service.stream_schedule_from_airport(
                    airport_code=airport_code.upper(),
                    from_local_datetime=parsed_from_dt,
                    to_local_datetime=parsed_to_dt,
                    limit=limit,
                    force_refresh=force_refresh,
                ):
                    yield batch.model_dump_json() + "\n"
            except Exception as e:
                logger.error(f"Stream error for {airport_code}: {str(e)}")
                yield json.dumps({"success": False, "error": str(e)}) + "\n"

        return StreamingResponse(response_generator(), media_type="application/x-ndjson")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schedule for {airport_code}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
