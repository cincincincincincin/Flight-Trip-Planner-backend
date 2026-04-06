from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from src.models.offer import FlightOffer

class FlightTime(BaseModel):
    # Szczegółowe informacje o czasie operacji lotniczej
    # Przechowuje zarówno czas uniwersalny (UTC), jak i czas lokalny dla lotniska
    
    utc: Optional[datetime] = Field(default=None, description="Time in UTC standard")
    local: Optional[datetime] = Field(default=None, description="Time in the airport's local timezone")

class FlightBase(BaseModel):
    # Podstawowy model lotu używany w harmonogramach
    # Definiuje trasę, numer lotu oraz kluczowe momenty podróży
    
    flight_number: str = Field(..., description="Unique flight identifier")
    airline_code: Optional[str] = Field(default=None, description="IATA code of the airline operating the flight")
    origin_airport_code: str = Field(..., description="Departure airport IATA code")
    destination_airport_code: str = Field(..., description="Arrival airport IATA code")
    scheduled_departure_utc: datetime = Field(..., description="UTC departure time")
    scheduled_departure_local: Optional[datetime] = Field(default=None, description="Local departure time")
    scheduled_arrival_utc: Optional[datetime] = Field(default=None, description="UTC arrival time")
    scheduled_arrival_local: Optional[datetime] = Field(default=None, description="Local arrival time")
    departure_terminal: Optional[str] = Field(default=None, description="Departure terminal info")
    departure_gate: Optional[str] = Field(default=None, description="Departure gate info")

class Flight(FlightBase):
    # Pełny model lotu wzbogacony o dane geograficzne i systemowe
    # Wykorzystywany do wyświetlania kart lotów w interfejsie użytkownika
    
    id: Optional[int] = Field(default=None, description="Internal system database ID")
    search_date: Optional[date] = Field(default=None, description="Date when this flight was searched for")
    created_at: Optional[datetime] = Field(default=None, description="Timestamp of record creation")

    # Dane o nazwach miast, państw i przewoźników pobierane z bazy danych
    origin_city_code: Optional[str] = Field(default=None, description="IATA code of the departure city")
    destination_city_code: Optional[str] = Field(default=None, description="IATA code of the arrival city")
    airline_name: Optional[str] = Field(default=None, description="Full name of the airline")

    # from_attributes=True pozwala modelowi na tworzenie nowych obiektów bezpośrednio na podstawie
    # atrybutów bazy danych lub innych klas, zamiast tylko ze standardowych słowników Pythona.
    model_config = ConfigDict(from_attributes=True)

class FlightResponse(BaseModel):
    # Standardowy kontener odpowiedzi API dla pojedynczego obiektu lotu
    success: bool = Field(default=True, description="Operation success status")
    data: Flight = Field(..., description="Detailed flight schedule data")

class FlightsResponse(BaseModel):
    # Kontener odpowiedzi API dla listy lotów wraz z informacją o stanie synchronizacji
    success: bool = Field(default=True, description="Operation success status")
    data: List[Flight] = Field(..., description="List of individual flight schedules")
    count: int = Field(..., description="Total number of flight records")
    last_fetched_at: Optional[datetime] = Field(default=None, description="Last data synchronization timestamp")
    range_end_datetime: Optional[str] = Field(default=None, description="ISO timestamp for the end of the fetched time window")

class FlightWithOffer(BaseModel):
    # Zintegrowany model łączący harmonogram lotu z opcjonalną wyceną
    # Kluczowy obiekt przesyłany do frontendu w celu pokazania lotu wraz z aktualną ceną
    
    flight: Flight = Field(..., description="Detailed flight schedule data")
    offer: Optional[FlightOffer] = Field(default=None, description="Linked pricing offer details")

class FlightsWithOffersResponse(BaseModel):
    # Zbiorcza odpowiedź API zawierająca loty wraz z ich ofertami cenowymi
    success: bool = Field(default=True, description="Operation success status")
    data: List[FlightWithOffer] = Field(..., description="List of flights paired with their offers")
    count: int = Field(..., description="Total record count")
    schedules_last_fetched_at: Optional[datetime] = Field(default=None, description="Schedules synchronization timestamp")
    prices_last_fetched_at: Optional[datetime] = Field(default=None, description="Prices synchronization timestamp")

class CacheInfo(BaseModel):
    # Uniwersalna struktura opisująca stan pamięci podręcznej dla dowolnego typu danych
    
    has_cache: bool = Field(..., description="Indicates if valid cache exists")
    last_fetched_at: Optional[datetime] = Field(default=None, description="Last cache update timestamp")
    records_count: Optional[int] = Field(default=None, description="Number of stored records")

class AirportSchedulesCacheInfo(BaseModel):
    # Szczegółowe metadane cache'owania dla harmonogramów konkretnego lotniska
    
    airport_code: str = Field(..., description="3-letter IATA airport code")
    search_date: date = Field(..., description="Date of the scheduled operations")
    direction: str = Field(..., description="Flight flow direction (Departure/Arrival)")
    cache_info: CacheInfo = Field(..., description="General cache status details")
