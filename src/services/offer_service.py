from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date, timedelta
from src.database import db
from src.models.offer import Offer, OfferCacheInfo
from src.services.api_client import aviasales_client
from src.config import settings
from src.cache import cache
import logging
import json
import pytz
import time as time_module

logger = logging.getLogger(__name__)

# Flaga debugowania: True wyświetla logi diagnostyczne dla serwisu cen
DEBUG_OFFER_SERVICE = settings.debug_price_service

def debug_log(message: str):
    if DEBUG_OFFER_SERVICE:
        logger.debug(message)


class OfferService:
    # Serwis do zarządzania ofertami cenowymi pobieranymi z API Aviasales

    @staticmethod
    async def get_cache_info(
        origin_city_code: str,
        destination_city_code: str,
        departure_date: date,
        currency: str = settings.default_currency
    ) -> OfferCacheInfo:
        # Zwraca informacje o stanie cache dla konkretnej trasy i daty
        async with db.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT last_fetched_at
                FROM flight_prices_cache
                WHERE origin_city_code = $1
                  AND destination_city_code = $2
                  AND departure_date = $3
                  AND currency = $4
            """, origin_city_code, destination_city_code, departure_date, currency.upper())

            if row:
                # Sprawdzamy liczbę rekordów w tabeli flight_offers zamiast w JSONB
                records_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM flight_offers
                    WHERE origin_city_code = $1 AND destination_city_code = $2 AND DATE(departure_at) = $3 AND currency = $4
                """, origin_city_code, destination_city_code, departure_date, currency.upper())

                return OfferCacheInfo(
                    origin_city_code=origin_city_code,
                    destination_city_code=destination_city_code,
                    departure_date=departure_date,
                    has_cache=True,
                    last_fetched_at=row['last_fetched_at'],
                    records_count=records_count or 0
                )

            return OfferCacheInfo(
                origin_city_code=origin_city_code,
                destination_city_code=destination_city_code,
                departure_date=departure_date,
                has_cache=False
            )

    @staticmethod
    async def is_cache_valid(
        origin_city_code: str,
        destination_city_code: str,
        departure_date: date,
        currency: str = settings.default_currency
    ) -> Tuple[bool, Optional[datetime]]:
        # Sprawdza czy cache cen jest jeszcze aktualny na podstawie reguł TTL
        date_iso = departure_date.isoformat()
        redis_key = f"prices:{origin_city_code}:{destination_city_code}:{date_iso}:{currency.upper()}"
        
        # Próbujemy najpierw sprawdzić w szybkim cache'u Redis
        if cache.is_ready:
            redis_data = await cache.get(redis_key)
            if redis_data:
                debug_log(f"Redis Price Cache HIT for {origin_city_code}->{destination_city_code} @ {date_iso}")
                return True, datetime.fromisoformat(redis_data['last_fetched_at'])
            
            # Jeśli Redis działa i nie ma klucza, uznajemy to za brak cache'u (Zero-Waste)
            return False, None

        # Jak nie ma w Redisie (lub leży), to sprawdzamy w bazie SQL
        async with db.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT last_fetched_at as last_fetched
                FROM flight_prices_cache
                WHERE origin_city_code = $1
                  AND destination_city_code = $2
                  AND departure_date = $3
                  AND currency = $4
            """, origin_city_code, destination_city_code, departure_date, currency.upper())

        if not row or not row['last_fetched']:
            return False, None

        last_fetched = row['last_fetched']
        
        # Sprawdzamy czy mamy jakiekolwiek oferty dla tej trasy
        async with db.get_connection() as conn:
            offers_exist = await conn.fetchval("""
                SELECT EXISTS(
                    SELECT 1 FROM flight_offers 
                    WHERE origin_city_code = $1 AND destination_city_code = $2 AND DATE(departure_at) = $3 AND currency = $4
                )
            """, origin_city_code, destination_city_code, departure_date, currency.upper())
        
        is_empty = not offers_exist
        now_utc = datetime.now(pytz.UTC)
        is_near = departure_date <= (now_utc.date() + timedelta(days=1))
        
        # Dynamiczne ustawianie ważności cache (pusty/bliski/daleki termin)
        if is_empty:
            expiry_delta = timedelta(hours=settings.price_cache_empty_ttl_hours)
        elif is_near:
            expiry_delta = timedelta(minutes=settings.price_cache_near_expiry_minutes)
        else:
            expiry_delta = timedelta(hours=settings.price_cache_far_expiry_hours)

        expiry_time = last_fetched + expiry_delta
        is_valid = datetime.now(last_fetched.tzinfo) < expiry_time
        
        return is_valid, last_fetched

    @staticmethod
    async def cleanup_expired_cache():
        # Czyści przedawnione wpisy o cenach z bazy danych
        async with db.get_connection() as conn:
            deleted_count = await conn.execute(f"""
                DELETE FROM flight_prices_cache fpc
                WHERE 
                    (EXISTS(SELECT 1 FROM flight_offers fo WHERE fo.origin_city_code = fpc.origin_city_code AND fo.destination_city_code = fpc.destination_city_code AND DATE(fo.departure_at) = fpc.departure_date AND fo.currency = fpc.currency) AND (
                        (departure_date <= (CURRENT_DATE + 1) AND last_fetched_at < (NOW() - INTERVAL '{settings.price_cache_near_expiry_minutes} minute'))
                        OR
                        (departure_date > (CURRENT_DATE + 1) AND last_fetched_at < (NOW() - INTERVAL '{settings.price_cache_far_expiry_hours} hour'))
                    ))
                    OR
                    (NOT EXISTS(SELECT 1 FROM flight_offers fo WHERE fo.origin_city_code = fpc.origin_city_code AND fo.destination_city_code = fpc.destination_city_code AND DATE(fo.departure_at) = fpc.departure_date AND fo.currency = fpc.currency) AND last_fetched_at < (NOW() - INTERVAL '{settings.price_cache_empty_ttl_hours} hour'))
            """)
            if deleted_count != "DELETE 0":
                debug_log(f"Cleaned up expired offer cache: {deleted_count}")

    @staticmethod
    def _parse_offer_from_api(
        offer_data: Dict[str, Any],
        origin_city_code: str,
        destination_city_code: str,
        currency: str = settings.default_currency
    ) -> Optional[Dict[str, Any]]:
        # Przerabia surowe dane z API zewnętrzne na nasz format wewnętrzny
        try:
            origin_airport = offer_data.get('origin_airport')
            destination_airport = offer_data.get('destination_airport')
            price = offer_data.get('price')
            
            if not origin_airport or not destination_airport or not price:
                return None

            departure_at = offer_data.get('departure_at')
            try:
                departure_str = str(departure_at).replace('Z', '')
                departure_dt = datetime.fromisoformat(departure_str).replace(tzinfo=None)
                departure_dt = departure_dt.replace(second=0, microsecond=0)
            except Exception as e:
                debug_log(f"Error parsing local departure time: {e}")
                return None

            if offer_data.get('transfers', 0) > 0:
                return None

            airline_code = offer_data.get('airline', '')
            raw_fn = str(offer_data.get('flight_number', ''))
            
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
                'link': offer_data.get('link')
            }
        except Exception as e:
            logger.error(f"Error parsing offer: {str(e)}")
            return None

    @staticmethod
    async def _save_offers_to_db(conn, offers_data: List[Dict[str, Any]]) -> int:
        # Zapisuje przetworzone oferty do bazy danych (operacja Upsert)
        saved_count = 0
        for offer_data in offers_data:
            try:
                await conn.execute("""
                    INSERT INTO flight_offers (
                        origin_city_code, destination_city_code,
                        origin_airport_code, destination_airport_code,
                        price, currency, airline_code, 
                        flight_number, departure_at, link
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
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
                    offer_data['link']
                )
                saved_count += 1
            except Exception as e:
                logger.error(f"Error saving offer: {str(e)}")
                raise
        return saved_count

    @staticmethod
    async def fetch_and_cache_offers(
        origin_city_code: str,
        destination_city_code: str,
        departure_date: date,
        currency: str = settings.default_currency
    ) -> Tuple[bool, Optional[datetime]]:
        # Pobiera świeże ceny z API i odświeża cache (Redis + SQL)
        await OfferService.cleanup_expired_cache()
        debug_log(f"Fetching offers for {origin_city_code}->{destination_city_code}")

        departure_at = departure_date.strftime("%Y-%m-%d")
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
            return False, None

        offers_data = []
        for offer in api_response.get('data', []):
            parsed = OfferService._parse_offer_from_api(offer, origin_city_code, destination_city_code, currency)
            if parsed:
                offers_data.append(parsed)

        if offers_data:
            async with db.get_connection() as conn:
                await OfferService._save_offers_to_db(conn, offers_data)

        now_utc = datetime.now(pytz.UTC)
        is_near = departure_date <= (now_utc.date() + timedelta(days=1))
        is_empty = len(api_response.get('data', [])) == 0
        
        if is_empty:
            ttl_sec = int(settings.price_cache_empty_ttl_hours * 3600)
        elif is_near:
            ttl_sec = int(settings.price_cache_near_expiry_minutes * 60)
        else:
            ttl_sec = int(settings.price_cache_far_expiry_hours * 3600)

        # Aktualizacja szybkiego cache'u w Redisie
        if cache.is_ready:
            date_iso = departure_date.isoformat()
            redis_key = f"prices:{origin_city_code}:{destination_city_code}:{date_iso}:{currency.upper()}"
            await cache.set(redis_key, {"last_fetched_at": now_utc.isoformat()}, ttl=ttl_sec)
        else:
            # Rezerwowy zapis do bazy SQL jeśli Redis nie jest dostępny
            async with db.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO flight_prices_cache 
                    (origin_city_code, destination_city_code, departure_date, currency, last_fetched_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (origin_city_code, destination_city_code, departure_date, currency)
                    DO UPDATE SET
                        last_fetched_at = EXCLUDED.last_fetched_at
                """, origin_city_code, destination_city_code, departure_date, currency.upper(), now_utc)

        return True, now_utc

    @staticmethod
    async def get_offers_for_route(
        origin_airport_code: str,
        destination_airport_code: str,
        departure_at: datetime,
        flight_number: Optional[str] = None,
        origin_city_code: Optional[str] = None,
        destination_city_code: Optional[str] = None,
        currency: str = settings.default_currency,
        force_refresh: bool = False
    ) -> Optional[Offer]:
        # Pobiera najlepszą ofertę dla konkretnej trasy i czasu (Smart Match)
        departure_date = departure_at.date()
        
        if not origin_city_code or not destination_city_code:
            async with db.get_connection() as conn:
                if not origin_city_code:
                    origin_city_code = await conn.fetchval("SELECT city_code FROM airports WHERE code = $1", origin_airport_code)
                if not destination_city_code:
                    destination_city_code = await conn.fetchval("SELECT city_code FROM airports WHERE code = $1", destination_airport_code)

        if not origin_city_code or not destination_city_code:
            return None

        # Sprawdzamy czy mamy świeży zestaw cen w cache'u
        cache_valid, last_fetched = await OfferService.is_cache_valid(origin_city_code, destination_city_code, departure_date, currency)

        if force_refresh or not cache_valid:
            success, last_fetched = await OfferService.fetch_and_cache_offers(origin_city_code, destination_city_code, departure_date, currency)

        if departure_at.tzinfo is not None:
            departure_at = departure_at.replace(tzinfo=None)

        async with db.get_connection() as conn:
            # Szukamy najtańszej oferty dopasowanej czasowo (okno +/- 5 minut)
            row = await conn.fetchrow("""
                SELECT
                    fo.origin_city_code, fo.destination_city_code,
                    fo.origin_airport_code, fo.destination_airport_code,
                    fo.price, fo.currency, fo.airline_code, 
                    fo.flight_number, fo.departure_at, fo.link
                FROM flight_offers fo
                WHERE fo.origin_airport_code = $1
                  AND fo.destination_airport_code = $2
                  AND fo.currency = $3
                  AND fo.departure_at BETWEEN ($4::TIMESTAMP - INTERVAL '5 minutes') 
                                      AND ($4::TIMESTAMP + INTERVAL '5 minutes')
                ORDER BY 
                    (fo.flight_number = $5) DESC,
                    fo.price ASC
                LIMIT 1
            """, origin_airport_code, destination_airport_code, currency.upper(), departure_at, flight_number)

            if not row:
                return None

            return Offer(**dict(row))

    @staticmethod
    async def get_offers_for_city_pair(
        origin_city_code: str,
        destination_city_code: str,
        departure_date: date,
        currency: str = settings.default_currency,
        force_refresh: bool = False
    ) -> List[Offer]:
        # Pobiera wszystkie dostępne oferty cenowe dla danej pary miast
        cache_valid, last_fetched = await OfferService.is_cache_valid(origin_city_code, destination_city_code, departure_date, currency)

        if force_refresh or not cache_valid:
            success, last_fetched = await OfferService.fetch_and_cache_offers(origin_city_code, destination_city_code, departure_date, currency)

        async with db.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT
                    fo.origin_city_code, fo.destination_city_code,
                    fo.origin_airport_code, fo.destination_airport_code,
                    fo.price, fo.currency, fo.airline_code, fo.flight_number,
                    fo.departure_at, fo.link
                FROM flight_offers fo
                WHERE fo.origin_city_code = $1
                  AND fo.destination_city_code = $2
                  AND DATE(fo.departure_at) = $3
                  AND fo.currency = $4
                ORDER BY fo.price ASC
            """, origin_city_code, destination_city_code, departure_date, currency.upper())

            return [Offer(**dict(row)) for row in rows]

# Globalny obiekt serwisu ofert
offer_service = OfferService()
