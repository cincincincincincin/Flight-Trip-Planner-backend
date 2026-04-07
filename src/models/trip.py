from pydantic import BaseModel
from typing import Optional, Any, List

class TripLeg(BaseModel):
    # Pojedynczy etap podróży między lotniskami
    fromAirportCode: str
    toAirportCode: str
    type: Optional[str] = "flight"
    flight: Optional[dict[str, Any]] = None

class TripStatePayload(BaseModel):
    # Przechowuje stan całego konfiguratora (start i odcinki)
    startAirport: dict[str, Any]
    legs: List[TripLeg]

class SaveTripRequest(BaseModel):
    # Żądanie zapisu trasy przez użytkownika
    name: Optional[str] = None
    trip_state: TripStatePayload

class TripResponse(BaseModel):
    # Kompletne dane trasy
    id: int
    user_id: str
    name: Optional[str]
    trip_state: dict[str, Any]
