from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime, date

class OfferBase(BaseModel):
    # Podstawowe dane o ofercie cenowej (trasa, cena, waluta)
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

class Offer(OfferBase):
    # Model rozszerzony o metadane systemowe
    id: Optional[int] = Field(default=None, description="Unique internal database ID")
    created_at: Optional[datetime] = Field(default=None, description="Timestamp of record creation")

    # Umożliwia tworzenie obiektów bezpośrednio z atrybutów bazy danych (JOIN)
    model_config = ConfigDict(from_attributes=True)

class OfferResponse(BaseModel):
    # Odpowiedź API dla pojedynczej oferty
    success: bool = Field(default=True, description="Operation success status")
    data: Offer = Field(..., description="Detailed flight offer data")

class OfferCacheInfo(BaseModel):
    # Informacja o stanie cache dla cen na danej trasie
    origin_city_code: str = Field(..., description="IATA code of the departure city")
    destination_city_code: str = Field(..., description="IATA code of the arrival city")
    departure_date: date = Field(..., description="Date of the scheduled departure")
    
    # Flaga has_cache mówi nam, czy w systemie są już jakieś dane dla tej trasy
    has_cache: bool = Field(..., description="Indicates if valid pricing data exists in cache")
    last_fetched_at: Optional[datetime] = Field(default=None, description="Timestamp of the most recent cache update")
    records_count: Optional[int] = Field(default=None, description="Number of pricing records currently stored")

class Offers(BaseModel):
    # Odpowiedź API dla listy ofert cenowych (zintegrowana z cache)
    success: bool = Field(default=True, description="Operation success status")
    data: List[Offer] = Field(..., description="List of individual flight offers")
    count: int = Field(..., description="Total number of offer records")
    last_fetched_at: Optional[datetime] = Field(default=None, description="Timestamp of the most recent data sync")
