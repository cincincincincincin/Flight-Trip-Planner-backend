from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from src.models.offer import Offer

class ScheduleTime(BaseModel):
    # Dane o czasie lotu
    utc: Optional[datetime] = Field(default=None, description="Time in UTC standard")
    local: Optional[datetime] = Field(default=None, description="Time in the airport's local timezone")

class FlightBase(BaseModel):
    # Dane lotu
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

class Flight(FlightBase):
    # Model lotu rozszerzony o dane z systemowej bazy danych
    id: Optional[int] = Field(default=None, description="Internal system database ID")
    created_at: Optional[datetime] = Field(default=None, description="Timestamp of record creation")

    # Umożliwia tworzenie obiektów bezpośrednio z atrybutów bazy danych (JOIN)
    model_config = ConfigDict(from_attributes=True)

class Schedule(BaseModel):
    # Odpowiedź API dla rozkładu lotów
    success: bool = Field(default=True, description="Operation success status")
    data: List[Flight] = Field(..., description="List of individual flights in the schedule")
    count: int = Field(..., description="Total number of flight records")
    last_fetched_at: Optional[datetime] = Field(default=None, description="Last data synchronization timestamp")
    range_end_datetime: Optional[str] = Field(default=None, description="ISO timestamp for the end of the fetched time window")

class AirportScheduleCacheInfo(BaseModel):
    # Stan cache dla rozkładu konkretnego lotniska
    airport_code: str = Field(..., description="3-letter IATA airport code")
    direction: str = Field(..., description="Flight flow direction (Departure/Arrival)")
    
    # Dane o stanie cache
    has_cache: bool = Field(..., description="Indicates if valid cache exists")
    last_fetched_at: Optional[datetime] = Field(default=None, description="Last cache update timestamp")
    records_count: Optional[int] = Field(default=None, description="Number of stored records")
