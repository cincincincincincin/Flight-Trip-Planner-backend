import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException, Request
from src.services.offer_service import offer_service
from src.limiter import limiter
from src.models.offer import Offers
from src.config import settings

logger = logging.getLogger(__name__)

# Endpointy do pobierania ofert cenowych (zintegrowane z API zewnętrznym i cache)
router = APIRouter(prefix="/offers", tags=["offers"])

@router.get("/", response_model=Offers)
@limiter.limit(settings.rate_limit_flights)
async def get_flight_offers(
    request: Request,
    origin: str = Query(..., description="Origin airport IATA code"),
    destination: str = Query(..., description="Destination airport IATA code"),
    departure_at: datetime = Query(..., description="Departure date and time with minute precision (ISO format)"),
    flight_number: Optional[str] = Query(None, description="Flight number for exact matching (e.g., 'LO 3905')"),
    currency: str = Query(settings.default_currency, description="Currency code: PLN, USD, EUR, GBP"),
    force_refresh: bool = Query(False, description="Force refresh from API")
):
    # Zwraca oferty cenowe dla konkretnej trasy i czasu wylotu
    # Wykorzystuje mechanizm Smart Match z oknem +/- 5 minut na backendzie
    try:
        return await offer_service.get_offers_for_route(
            origin_airport_code=origin.upper(),
            destination_airport_code=destination.upper(),
            departure_at=departure_at,
            flight_number=flight_number,
            currency=currency.upper(),
            force_refresh=force_refresh
        )
    except Exception as e:
        logger.error(f"Error getting offers for {origin}->{destination}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
