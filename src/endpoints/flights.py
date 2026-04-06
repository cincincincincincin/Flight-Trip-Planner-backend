import json
import logging
from typing import Optional
from datetime import date, datetime
from fastapi import APIRouter, Query, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from src.services.flight_schedule_service import flight_schedule_service
from src.services.flight_price_service import flight_price_service
from src.limiter import limiter
from src.models.flight import FlightsResponse
from src.models.offer import FlightOffersResponse
from src.config import settings

logger = logging.getLogger(__name__)

# Definicja routera dla operacji na lotach
router = APIRouter(prefix="/flights", tags=["flights"])

@router.get("/airport/{airport_code}")
@limiter.limit(settings.rate_limit_flights)
async def get_airport_flights(
    request: Request,
    airport_code: str = Path(..., description="IATA airport code (e.g., 'WAW')"),
    from_local_datetime: str = Query(..., description="Start of window in local airport time (YYYY-MM-DDTHH:MM:SS)."),
    to_local_datetime: str = Query(..., description="End of window in local airport time (YYYY-MM-DDTHH:MM:SS)."),
    search_date: Optional[date] = Query(None, description="Fallback: date to search (uses midnight). Ignored if from_local_datetime is provided."),
    limit: int = Query(200, ge=1, le=2000, description="Max results"),
    force_refresh: bool = Query(False, description="Force refresh from API")
):
    # Zwraca strumień lotów odlatujących z danego lotniska dla określonego przedziału czasowego.
    # Wyniki są przesyłane w formacie NDJSON dla zapewnienia płynności renderowania na frontendzie.
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
            # Generator asynchroniczny przetwarzający paczki danych z serwisu harmonogramów
            try:
                async for batch in flight_schedule_service.stream_flights_from_airport(
                    airport_code=airport_code.upper(),
                    from_local_datetime=parsed_from_dt,
                    to_local_datetime=parsed_to_dt,
                    limit=limit,
                    force_refresh=force_refresh,
                ):
                    yield batch.json() + "\n"
            except Exception as e:
                logger.error(f"Stream error for {airport_code}: {str(e)}")
                yield json.dumps({"success": False, "error": str(e)}) + "\n"

        return StreamingResponse(response_generator(), media_type="application/x-ndjson")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting flights for {airport_code}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/offers/{origin_airport}/{destination_airport}", response_model=FlightOffersResponse)
@limiter.limit(settings.rate_limit_flights)
async def get_flight_offers(
    request: Request,
    origin_airport: str = Path(..., description="Origin airport IATA code"),
    destination_airport: str = Path(..., description="Destination airport IATA code"),
    departure_at: datetime = Query(..., description="Departure date and time with minute precision (ISO format)"),
    currency: str = Query(settings.default_currency, description="Currency code: PLN, USD, EUR, GBP"),
    force_refresh: bool = Query(False, description="Force refresh from API")
):
    # Zwraca oferty cenowe lotów dla konkretnej trasy między lotniskami.
    try:
        return await flight_price_service.get_offers_for_route(
            origin_airport_code=origin_airport.upper(),
            destination_airport_code=destination_airport.upper(),
            departure_at=departure_at,
            currency=currency.upper(),
            force_refresh=force_refresh
        )
    except Exception as e:
        logger.error(f"Error getting offers for {origin_airport}->{destination_airport}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
