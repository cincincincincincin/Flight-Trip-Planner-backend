from fastapi import APIRouter, Query, HTTPException, Path, Request
from typing import Optional
from datetime import date, datetime
from src.services.flight_schedule_service import FlightScheduleService
from src.services.flight_price_service import flight_price_service
from src.limiter import limiter
from src.models.flight import FlightsResponse, FlightOffersResponse
from src.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flights", tags=["flights"])


@router.get("/airport/{airport_code}", response_model=FlightsResponse)
@limiter.limit(settings.rate_limit_flights)
async def get_airport_flights(
    request: Request,
    airport_code: str = Path(..., description="IATA airport code (e.g., 'WAW')"),
    from_local_datetime: Optional[str] = Query(None, description="Start of 12h window in local airport time (YYYY-MM-DDTHH:MM:SS). If omitted, uses current time."),
    search_date: Optional[date] = Query(None, description="Fallback: date to search (uses midnight). Ignored if from_local_datetime is provided."),
    limit: int = Query(200, ge=1, le=2000, description="Max results (default 200 for full 12h window)"),
    force_refresh: bool = Query(False, description="Force refresh from API"),
    lang: str = Query('en', description="Language for localized city/airport names (en/pl)")
):
    """
    Get departing flights from airport for a 12h window starting at from_local_datetime.

    - Returns all flights in the 12h window (no offset pagination)
    - Returns range_end_datetime for the next window request
    - Automatically fetches from API if no valid cache covers the requested datetime
    """
    try:
        # Parse from_local_datetime string to datetime object
        parsed_from_dt = None
        if from_local_datetime:
            try:
                parsed_from_dt = datetime.fromisoformat(from_local_datetime)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid from_local_datetime format: {from_local_datetime}. Use YYYY-MM-DDTHH:MM:SS")

        return await FlightScheduleService.get_flights_from_airport(
            airport_code=airport_code.upper(),
            from_local_datetime=parsed_from_dt,
            search_date=search_date,
            limit=limit,
            force_refresh=force_refresh,
            lang=lang
        )
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
    departure_date: date = Query(default_factory=date.today, description="Departure date"),
    currency: str = Query(settings.default_currency, description="Currency code: PLN, USD, EUR, GBP"),
    force_refresh: bool = Query(False, description="Force refresh from API")
):
    """
    Get flight offers (prices) for a specific airport-to-airport route

    - Fetches prices from Aviasales API
    - Returns only direct flights (no transfers)
    - Filters results for specific airports (important for cities with multiple airports)
    """
    try:
        return await flight_price_service.get_offers_for_route(
            origin_airport_code=origin_airport.upper(),
            destination_airport_code=destination_airport.upper(),
            departure_date=departure_date,
            currency=currency.upper(),
            force_refresh=force_refresh
        )
    except Exception as e:
        logger.error(f"Error getting offers for {origin_airport}->{destination_airport}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


