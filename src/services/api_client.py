import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from src.config import settings
import logging

logger = logging.getLogger(__name__)

# Flaga debugowania: True włącza logi diagnostyczne dla wszystkich zapytań API
DEBUG_API_CALLS = settings.debug_api_calls

def debug_log(message: str):
    # Wyświetla logi diagnostyczne w konsoli, jeśli flaga debugowania jest włączona
    if DEBUG_API_CALLS:
        logger.debug(message)

class AeroDataBoxClient:
    # Klient do API AeroDataBox (RapidAPI) obsługujący rozkłady lotów
    # Służy do wyciągania danych o odlotach, przylotach i lotniskach

    BASE_URL = settings.aerodatabox_base_url

    def __init__(self):
        # Konfiguracja autoryzacji na podstawie kluczy z config
        self.api_key = settings.aerodatabox_api_key
        self.rapidapi_host = settings.rapidapi_host
        self.headers = {
            "Accept": "application/json",
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": self.rapidapi_host
        }

    async def get_airport_departures(
        self,
        airport_code: str,
        from_local: str,
        to_local: str,
        direction: str = "Departure",
        with_cancelled: bool = False,
        with_cargo: bool = False,
        with_codeshared: bool = True,
        with_leg: bool = True,
        with_private: bool = False
    ) -> Optional[Dict[str, Any]]:
        # Pobiera listę lotów (odloty/przyloty) dla danego lotniska w oknie czasowym (max 12h)
        url = f"{self.BASE_URL}/flights/airports/iata/{airport_code}/{from_local}/{to_local}"

        params = {
            "direction": direction,
            "withCancelled": str(with_cancelled).lower(),
            "withCargo": str(with_cargo).lower(),
            "withCodeshared": str(with_codeshared).lower(),
            "withLeg": str(with_leg).lower(),
            "withPrivate": str(with_private).lower()
        }

        debug_log(f"AeroDataBox API call: {url} with params: {params}")

        try:
            async with httpx.AsyncClient(timeout=settings.aerodatabox_timeout) as client:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                # Zwraca pustą listę lotów jeśli API odpowie kodem 204
                if response.status_code == 204:
                    debug_log(f"AeroDataBox API returned 204 No Content for {airport_code}: no flights")
                    return {"departures": [], "arrivals": []}
                data = response.json()
                debug_log(f"AeroDataBox API response: {len(data.get('departures', []) + data.get('arrivals', []))} flights")
                return data
        except httpx.HTTPStatusError as e:
            logger.error(f"AeroDataBox API HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"AeroDataBox API request error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"AeroDataBox API unexpected error: {str(e)}")
            return None


class AviasalesClient:
    # Klient do API Aviasales (Travelpayouts) do pobierania cen biletów
    # Pozwala na sprawdzanie ofert cenowych na konkretnych trasach między miastami

    BASE_URL = settings.aviasales_base_url

    def __init__(self):
        # Inicjalizacja tokena do autoryzacji zapytań
        self.api_token = settings.aviasales_api_token

    async def get_flight_prices(
        self,
        origin: str,
        destination: str,
        departure_at: str,
        currency: str = "USD",
        one_way: bool = True,
        direct: bool = True,
        limit: int = 1000,
        sorting: str = "price"
    ) -> Optional[Dict[str, Any]]:
        # Pobiera aktualne zestawienie cen biletów dla wybranej trasy i daty wylotu
        params = {
            "origin": origin,
            "destination": destination,
            "departure_at": departure_at,
            "currency": currency.lower(),
            "one_way": str(one_way).lower(),
            "direct": str(direct).lower(),
            "limit": limit,
            "sorting": sorting,
            "token": self.api_token
        }

        debug_log(f"Aviasales API call: {self.BASE_URL} with params: {params}")

        try:
            async with httpx.AsyncClient(timeout=settings.aviasales_timeout) as client:
                response = await client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

                if not data.get("success", False):
                    logger.error(f"Aviasales API returned success=false: {data.get('error', 'Unknown error')}")
                    return None

                debug_log(f"Aviasales API response: {len(data.get('data', []))} offers")
                return data
        except httpx.HTTPStatusError as e:
            logger.error(f"Aviasales API HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Aviasales API request error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Aviasales API unexpected error: {str(e)}")
            return None


# Globalne obiekty klientów używane w całej aplikacji
aerodatabox_client = AeroDataBoxClient()
aviasales_client = AviasalesClient()
