from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class Flight(BaseModel):
    # Podstawowe dane lotu
    flight_number: str = Field(..., description="Unique flight identifier")
    airline_code: Optional[str] = Field(default=None, description="IATA code of the airline operating the flight")
    airline_name: Optional[str] = Field(default=None, description="Full name of the airline")
    origin_airport_code: str = Field(..., description="Departure airport IATA code")
    destination_airport_code: str = Field(..., description="Arrival airport IATA code")
    scheduled_departure_utc: datetime = Field(..., description="UTC departure time")
    scheduled_departure_local: Optional[datetime] = Field(default=None, description="Local departure time")
    scheduled_arrival_utc: Optional[datetime] = Field(default=None, description="UTC arrival time")
    scheduled_arrival_local: Optional[datetime] = Field(default=None, description="Local arrival time")
    departure_terminal: Optional[str] = Field(default=None, description="Departure terminal info")
    departure_gate: Optional[str] = Field(default=None, description="Departure gate info")

class Schedule(BaseModel):
    # Batch danych rozkładowych przesyłany w NDJSON
    success: bool = Field(default=True, description="Operation success status")
    data: List[Flight] = Field(..., description="List of individual flights in the schedule")
    count: int = Field(..., description="Total number of flight records")
    last_fetched_at: Optional[datetime] = Field(default=None, description="Last data synchronization timestamp")
    range_end_datetime: Optional[str] = Field(default=None, description="ISO timestamp for the end of the fetched time window")

class AirportScheduleCacheInfo(BaseModel):
    # Stan cache dla rozkładu konkretnego lotniska
    airport_code: str = Field(..., description="3-letter IATA airport code")
    direction: str = Field(..., description="Flight flow direction (Departure/Arrival)")
    has_cache: bool = Field(..., description="Indicates if valid cache exists")
    last_fetched_at: Optional[datetime] = Field(default=None, description="Last cache update timestamp")
    records_count: Optional[int] = Field(default=None, description="Number of stored records")
