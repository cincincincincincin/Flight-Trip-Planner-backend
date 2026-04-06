from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime, date

class FlightOfferBase(BaseModel):
    # Podstawowy model oferty cenowej dla konkretnej trasy lotniczej
    # Zawiera minimalny zestaw danych niezbędny do identyfikacji połączenia i jego ceny
    
    origin_city_code: str = Field(..., description="IATA code of the departure city")
    destination_city_code: str = Field(..., description="IATA code of the arrival city")
    origin_airport_code: str = Field(..., description="IATA code of the departure airport")
    destination_airport_code: str = Field(..., description="IATA code of the arrival airport")
    price: float = Field(..., description="Flight ticket price")
    currency: str = Field(..., description="Currency code (e.g. PLN, EUR)")
    airline_code: Optional[str] = Field(default=None, description="IATA code of the airline")
    flight_number: Optional[str] = Field(default=None, description="Flight number identifier")
    departure_at: datetime = Field(..., description="Scheduled departure time")
    link: Optional[str] = Field(default=None, description="Direct booking link provided by the external API")

class FlightOffer(FlightOfferBase):
    # Rozszerzony model oferty cenowej wzbogacony o metadane bazy danych
    # Wykorzystywany do prezentacji pełnych informacji na frontonowej liście lotów
    
    id: Optional[int] = Field(default=None, description="Unique internal database ID")
    search_date: Optional[date] = Field(default=None, description="Date when the search was performed")
    created_at: Optional[datetime] = Field(default=None, description="Timestamp of record creation")

    # Dodatkowe nazwy geograficzne pobierane podczas złączeń tabel bazy danych
    airline_name: Optional[str] = Field(default=None, description="Full name of the airline")

    # from_attributes=True pozwala modelowi na tworzenie nowych obiektów bezpośrednio na podstawie
    # atrybutów bazy danych lub innych klas, zamiast tylko ze standardowych słowników Pythona.
    model_config = ConfigDict(from_attributes=True)

class FlightOfferResponse(BaseModel):
    # Standardowy kontener odpowiedzi API dla pojedynczej oferty cenowej
    success: bool = Field(default=True, description="Operation success status")
    data: FlightOffer = Field(..., description="Detailed flight offer data")

class FlightOffersResponse(BaseModel):
    # Standardowy kontener odpowiedzi API dla listy ofert cenowych
    success: bool = Field(default=True, description="Operation success status")
    data: List[FlightOffer] = Field(..., description="List of flight offer objects")
    count: int = Field(..., description="Total number of offers found")
    last_fetched_at: Optional[datetime] = Field(default=None, description="Timestamp of the last data synchronization")

class FlightPricesCacheInfo(BaseModel):
    # Model informacyjny o stanie pamięci podręcznej dla cen na danej trasie
    # Pomaga systemowi zdecydować, czy konieczne jest ponowne pobranie danych z zewnętrznego API
    
    origin_city_code: str = Field(..., description="IATA code of the departure city")
    destination_city_code: str = Field(..., description="IATA code of the arrival city")
    departure_date: date = Field(..., description="Date of the scheduled departure")
    
    # has_cache informuje czy w systemie istnieją już jakiekolwiek dane dla tej trasy
    has_cache: bool = Field(..., description="Indicates if valid pricing data exists in cache")
    last_fetched_at: Optional[datetime] = Field(default=None, description="Timestamp of the most recent cache update")
    records_count: Optional[int] = Field(default=None, description="Number of pricing records currently stored")
