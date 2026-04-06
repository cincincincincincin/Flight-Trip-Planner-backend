from pydantic import BaseModel
from typing import Optional, Any, List
from datetime import datetime

class TripLeg(BaseModel):
    # Model reprezentujący pojedynczy odcinek podróży między lotniskami
    fromAirportCode: str
    toAirportCode: str
    type: Optional[str] = "flight"
    flight: Optional[dict[str, Any]] = None

class TripStatePayload(BaseModel):
    # Struktura przechowująca stan konfiguratora podróży (lotnisko startowe i odcinki)
    startAirport: dict[str, Any]
    legs: List[TripLeg]

class SaveTripRequest(BaseModel):
    # Żądanie zapisu nowej podróży zawierające nazwę, stan oraz wygenerowane trasy
    name: Optional[str] = None
    trip_state: TripStatePayload
    trip_routes: List[dict[str, Any]]

class TripResponse(BaseModel):
    # Pełna odpowiedź serwera zawierająca identyfikatory bazy danych i daty utworzenia
    id: int
    user_id: str
    name: Optional[str]
    trip_state: dict[str, Any]
    trip_routes: List[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
