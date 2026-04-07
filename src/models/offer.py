from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date

class Offer(BaseModel):
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

class OfferCacheInfo(BaseModel):
    # Informacja o stanie cache dla cen na danej trasie
    origin_city_code: str = Field(..., description="IATA code of the departure city")
    destination_city_code: str = Field(..., description="IATA code of the arrival city")
    departure_date: date = Field(..., description="Date of the scheduled departure")
    has_cache: bool = Field(..., description="Indicates if valid pricing data exists in cache")
    last_fetched_at: Optional[datetime] = Field(default=None, description="Timestamp of the most recent cache update")
    records_count: Optional[int] = Field(default=None, description="Number of pricing records currently stored")
