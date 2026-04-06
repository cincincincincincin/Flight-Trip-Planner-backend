from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date, timedelta
from src.database import db
from src.models.flight import CacheInfo
from src.models.offer import FlightOffer, FlightOffersResponse, FlightPricesCacheInfo
from src.services.api_client import aviasales_client
from src.config import settings
import logging
import json

logger = logging.getLogger(__name__)

# Flaga debugowania: ustawienie na False wyłącza logi diagnostyczne serwisu cen
DEBUG_PRICE_SERVICE = settings.debug_price_service

def debug_log(message: str):
    # Loguje komunikat diagnostyczny jeśli DEBUG_PRICE_SERVICE jest aktywny
    if DEBUG_PRICE_SERVICE:
        logger.debug(message)


class FlightPriceService:
    # Serwis zarządzający ofertami cenowymi lotów pobieranymi z API Aviasales

    # Czas wygasania pamięci podręcznej cen wyrażony w godzinach
    CACHE_EXPIRY_HOURS = settings.price_cache_expiry_hours

    @staticmethod
    async def get_cache_info(
        origin_city_code: str,
        destination_city_code: str,
        departure_date: date
    ) -> CacheInfo:
        # Zwraca metadane dotyczące stanu pamięci podręcznej dla konkretnej trasy i daty
        async with db.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT last_fetched_at,
                       jsonb_array_length(data->'data') as records_count
                FROM flight_prices_cache
                WHERE origin_city_code = $1
                  AND destination_city_code = $2
                  AND departure_date = $3
            """, origin_city_code, destination_city_code, departure_date)

            if row:
                return CacheInfo(
                    has_cache=True,
                    last_fetched_at=row['last_fetched_at'],
                    records_count=row['records_count']
                )

            return CacheInfo(has_cache=False)

    @staticmethod
    async def is_cache_valid(
        origin_city_code: str,
        destination_city_code: str,
        departure_date: date,
        currency: str = settings.default_currency
    ) -> Tuple[bool, Optional[datetime]]:
        # Weryfikuje czy wpis w pamięci podręcznej istnieje i czy nie przekroczył czasu ważności
        async with db.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT last_fetched_at as last_fetched
                FROM flight_prices_cache
                WHERE origin_city_code = $1
                  AND destination_city_code = $2
                  AND departure_date = $3
            """, origin_city_code, destination_city_code, departure_date)

        if not row or not row['last_fetched']:
            debug_log(f"No price cache for {origin_city_code}->{destination_city_code} on {departure_date}")
            return False, None

        last_fetched = row['last_fetched']
        expiry_time = last_fetched + timedelta(hours=FlightPriceService.CACHE_EXPIRY_HOURS)
        is_valid = datetime.now(last_fetched.tzinfo) < expiry_time
        debug_log(
            f"Price cache for {origin_city_code}->{destination_city_code} [{currency}]: "
            f"fetched at {last_fetched}, expires at {expiry_time}, valid: {is_valid}"
        )
        return is_valid, last_fetched

    @staticmethod
    def _parse_offer_from_api(
        offer_data: Dict[str, Any],
        origin_city_code: str,
        destination_city_code: str,
        search_date: date,
        currency: str = settings.default_currency
    ) -> Optional[Dict[str, Any]]:
        # Przetwarza surową ofertę z API Aviasales na ustandaryzowany format wewnętrzny systemu
        try:
            # Weryfikacja obecności kluczowych pól niezbędnych do poprawnej identyfikacji lotu
            origin_airport = offer_data.get('origin_airport')
            destination_airport = offer_data.get('destination_airport')
            price = offer_data.get('price')
            departure_at = offer_data.get('departure_at')

            if not origin_airport or not destination_airport or not price or not departure_at:
                debug_log(f"Skipping offer: missing required data")
                return None

            # Konwersja czasu odlotu na obiekt świadomy strefy czasowej (UTC)
            departure_dt = datetime.fromisoformat(str(departure_at).replace('Z', '+00:00'))

            # Restrykcyjne filtrowanie: akceptujemy wyłącznie loty bezpośrednie bez przesiadek
            transfers = offer_data.get('transfers', 0)
            if transfers > 0:
                return None

            airline_code = offer_data.get('airline', '')
            raw_fn = str(offer_data.get('flight_number', ''))
            
            # Formatowanie numeru lotu do postaci ustandaryzowanej np. AA 123
            if airline_code and raw_fn and not raw_fn.startswith(airline_code):
                flight_number = f"{airline_code} {raw_fn}"
            else:
                flight_number = raw_fn

            return {
                'origin_city_code': origin_city_code,
                'destination_city_code': destination_city_code,
                'origin_airport_code': origin_airport,
                'destination_airport_code': destination_airport,
                'price': float(price),
                'currency': currency.upper(),
                'airline_code': airline_code,
                'flight_number': flight_number,
                'departure_at': departure_dt,
                'link': offer_data.get('link'),
                'search_date': search_date
            }
        except Exception as e:
            logger.error(f"Error parsing offer: {str(e)}")
            return None

    @staticmethod
    async def _save_offers_to_db(conn, offers_data: List[Dict[str, Any]]) -> int:
        # Zapisuje przetworzone oferty cenowe do bazy danych przy użyciu aktywnego połączenia
        # Metoda realizuje operację upsert zapewniając aktualność linków i czasów trwania podróży
        saved_count = 0
        for offer_data in offers_data:
            try:
                await conn.execute("""
                    INSERT INTO flight_offers (
                        origin_city_code, destination_city_code,
                        origin_airport_code, destination_airport_code,
                        price, currency, airline_code, flight_number,
                        departure_at, link, search_date
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (origin_airport_code, destination_airport_code, departure_at, flight_number, price)
                    DO UPDATE SET
                        link = EXCLUDED.link
                """,
                    offer_data['origin_city_code'],
                    offer_data['destination_city_code'],
                    offer_data['origin_airport_code'],
                    offer_data['destination_airport_code'],
                    offer_data['price'],
                    offer_data['currency'],
                    offer_data['airline_code'],
                    offer_data['flight_number'],
                    offer_data['departure_at'],
                    offer_data['link'],
                    offer_data['search_date']
                )
                saved_count += 1
            except Exception as e:
                logger.error(f"Error saving offer: {str(e)}")
                raise

        debug_log(f"Saved {saved_count} offers to database")
        return saved_count

    @staticmethod
    async def fetch_and_cache_prices(
        origin_city_code: str,
        destination_city_code: str,
        departure_date: date,
        currency: str = settings.default_currency
    ) -> Tuple[bool, Optional[datetime]]:
        # Pobiera aktualne ceny z API zewnętrznego i zapisuje je w pamięci podręcznej systemu
        debug_log(f"Fetching prices for {origin_city_code}->{destination_city_code} on {departure_date} in {currency}")

        # Formatowanie daty odlotu zgodnie z wymaganiami specyfikacji API
        departure_at = departure_date.strftime("%Y-%m-%d")

        # Wykonanie zapytania do serwisu Aviasales/Travelpayouts
        api_response = await aviasales_client.get_flight_prices(
            origin=origin_city_code,
            destination=destination_city_code,
            departure_at=departure_at,
            currency=currency,
            one_way=True,
            direct=True,
            limit=settings.aviasales_default_limit
        )

        if not api_response or not api_response.get('success'):
            logger.error(f"Failed to fetch prices from API for {origin_city_code}->{destination_city_code}")
            return False, None

        # Przetworzenie otrzymanych ofert przed rozpoczęciem operacji na bazie danych
        offers_data = []
        for offer in api_response.get('data', []):
            parsed = FlightPriceService._parse_offer_from_api(
                offer, origin_city_code, destination_city_code, departure_date, currency
            )
            if parsed:
                offers_data.append(parsed)

        # Atomowy zapis: aktualizacja metadanych cache oraz wstawienie nowych ofert w jednej transakcji
        async with db.get_connection() as conn:
            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO flight_prices_cache (origin_city_code, destination_city_code, departure_date, data)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (origin_city_code, destination_city_code, departure_date)
                    DO UPDATE SET
                        last_fetched_at = NOW(),
                        data = EXCLUDED.data
                """, origin_city_code, destination_city_code, departure_date, json.dumps(api_response))

                await FlightPriceService._save_offers_to_db(conn, offers_data)

        return True, datetime.now()

    @staticmethod
    async def get_offers_for_route(
        origin_airport_code: str,
        destination_airport_code: str,
        departure_at: datetime,
        origin_city_code: Optional[str] = None,
        destination_city_code: Optional[str] = None,
        currency: str = settings.default_currency,
        force_refresh: bool = False
    ) -> FlightOffersResponse:
        # Pobiera oferty cenowe dla konkretnej pary lotnisk i dokładnego czasu odlotu.
        # Metoda dopasowuje oferty z uwzględnieniem stref czasowych i waluty.
        departure_date = departure_at.date()
        
        # Pobranie brakujących kodów miast dla lotnisk jeśli nie zostały przekazane
        if not origin_city_code or not destination_city_code:
            async with db.get_connection() as conn:
                if not origin_city_code:
                    origin_city_code = await conn.fetchval(
                        "SELECT city_code FROM airports WHERE code = $1", origin_airport_code
                    )
                if not destination_city_code:
                    destination_city_code = await conn.fetchval(
                        "SELECT city_code FROM airports WHERE code = $1", destination_airport_code
                    )

        if not origin_city_code or not destination_city_code:
            logger.error(f"Could not find city codes for airports {origin_airport_code}, {destination_airport_code}")
            return FlightOffersResponse(data=[], count=0)

        # Sprawdzenie aktualności pamięci podręcznej dla wybranej waluty
        cache_valid, last_fetched = await FlightPriceService.is_cache_valid(
            origin_city_code, destination_city_code, departure_date, currency
        )

        # Odświeżenie danych z API w przypadku wymuszenia lub wygaśnięcia cache
        if force_refresh or not cache_valid:
            success, last_fetched = await FlightPriceService.fetch_and_cache_prices(
                origin_city_code, destination_city_code, departure_date, currency
            )
            if not success:
                debug_log("API fetch failed, returning cached data if available")

        # Pobranie dopasowanych ofert z bazy z rygorystycznym sprawdzeniem czasu i parametrów lotu
        async with db.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT
                    fo.id, fo.origin_city_code, fo.destination_city_code,
                    fo.origin_airport_code, fo.destination_airport_code,
                    fo.price, fo.currency, fo.airline_code, fo.flight_number,
                    fo.departure_at, fo.link,
                    fo.search_date, fo.created_at,
                    a.name as airline_name
                FROM flight_offers fo
                LEFT JOIN airlines a ON fo.airline_code = a.code
                LEFT JOIN airports oa ON fo.origin_airport_code = oa.code
                WHERE fo.origin_airport_code = $1
                  AND fo.destination_airport_code = $2
                  AND DATE(fo.departure_at AT TIME ZONE oa.time_zone) = $3
                  AND EXTRACT(HOUR FROM fo.departure_at AT TIME ZONE oa.time_zone) = EXTRACT(HOUR FROM $5::TIMESTAMP)
                  AND EXTRACT(MINUTE FROM fo.departure_at AT TIME ZONE oa.time_zone) = EXTRACT(MINUTE FROM $5::TIMESTAMP)
                  AND fo.transfers = 0
                  AND fo.currency = $4
                ORDER BY fo.price ASC
                LIMIT 1
            """, origin_airport_code, destination_airport_code, departure_date, currency.upper(), departure_at)

            offers = [FlightOffer(**dict(row)) for row in rows]

            return FlightOffersResponse(
                data=offers,
                count=len(offers),
                last_fetched_at=last_fetched
            )

    @staticmethod
    async def get_offers_for_city_pair(
        origin_city_code: str,
        destination_city_code: str,
        departure_date: date,
        currency: str = settings.default_currency,
        force_refresh: bool = False
    ) -> FlightOffersResponse:
        # Pobiera wszystkie dostępne oferty cenowe dla pary miast (wszystkie kombinacje lotnisk).
        # Implementuje logikę sprawdzania cache i opcjonalnego pobierania danych z API.
        cache_valid, last_fetched = await FlightPriceService.is_cache_valid(
            origin_city_code, destination_city_code, departure_date, currency
        )

        if force_refresh or not cache_valid:
            success, last_fetched = await FlightPriceService.fetch_and_cache_prices(
                origin_city_code, destination_city_code, departure_date, currency
            )
            if not success:
                debug_log("API fetch failed, returning cached data if available")

        # Zapytanie agregujące oferty dla całej aglomeracji miejskiej
        async with db.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT
                    fo.id, fo.origin_city_code, fo.destination_city_code,
                    fo.origin_airport_code, fo.destination_airport_code,
                    fo.price, fo.currency, fo.airline_code, fo.flight_number,
                    fo.departure_at, fo.link,
                    fo.search_date, fo.created_at,
                    a.name as airline_name,
                    oc.name as origin_city_name,
                    dc.name as destination_city_name,
                    oa.name as origin_airport_name,
                    da.name as destination_airport_name
                FROM flight_offers fo
                LEFT JOIN airlines a ON fo.airline_code = a.code
                LEFT JOIN cities oc ON fo.origin_city_code = oc.code
                LEFT JOIN cities dc ON fo.destination_city_code = dc.code
                LEFT JOIN airports oa ON fo.origin_airport_code = oa.code
                LEFT JOIN airports da ON fo.destination_airport_code = da.code
                WHERE fo.origin_city_code = $1
                  AND fo.destination_city_code = $2
                  AND DATE(fo.departure_at) = $3
                  AND fo.transfers = 0
                  AND fo.currency = $4
                ORDER BY fo.price ASC
            """, origin_city_code, destination_city_code, departure_date, currency.upper())

            offers = [FlightOffer(**dict(row)) for row in rows]

            return FlightOffersResponse(
                data=offers,
                count=len(offers),
                last_fetched_at=last_fetched
            )


# Globalna instancja serwisu zarządzania cenami
flight_price_service = FlightPriceService()

