from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date, timedelta
from src.database import db
from src.models.offer import Offer, Offers, OfferCacheInfo
from src.services.api_client import aviasales_client
from src.config import settings
from src.cache import cache
import logging
import json
import pytz
import time as time_module

logger = logging.getLogger(__name__)

# Flag debug: wyłącza logi diagnostyczne dla serwisu cen
DEBUG_OFFER_SERVICE = settings.debug_price_service

def debug_log(message: str):
    if DEBUG_OFFER_SERVICE:
        logger.debug(message)


class OfferService:
    # Serwis zarządzający ofertami cenowymi pobieranymi z API Aviasales

    @staticmethod
    async def get_cache_info(
        origin_city_code: str,
        destination_city_code: str,
        departure_date: date,
        currency: str = settings.default_currency
    ) -> OfferCacheInfo:
        # Zwraca metadane cache dla konkretnej trasy, daty i waluty
        async with db.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT last_fetched_at,
                       jsonb_array_length(data->'data') as records_count
                FROM flight_prices_cache
                WHERE origin_city_code = $1
                  AND destination_city_code = $2
                  AND departure_date = $3
                  AND currency = $4
            """, origin_city_code, destination_city_code, departure_date, currency.upper())

            if row:
                return OfferCacheInfo(
                    origin_city_code=origin_city_code,
                    destination_city_code=destination_city_code,
                    departure_date=departure_date,
                    has_cache=True,
                    last_fetched_at=row['last_fetched_at'],
                    records_count=row['records_count']
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
        # Sprawdza, czy cache cen jest jeszcze ważny według reguł TTL
        date_iso = departure_date.isoformat()
        redis_key = f"prices:{origin_city_code}:{destination_city_code}:{date_iso}:{currency.upper()}"
        
        if cache.is_ready:
            redis_data = await cache.get(redis_key)
            if redis_data:
                debug_log(f"Redis Price Cache HIT dla {origin_city_code}->{destination_city_code} @ {date_iso}")
                return True, datetime.fromisoformat(redis_data['last_fetched_at'])

        async with db.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT last_fetched_at as last_fetched, data
                FROM flight_prices_cache
                WHERE origin_city_code = $1
                  AND destination_city_code = $2
                  AND departure_date = $3
                  AND currency = $4
            """, origin_city_code, destination_city_code, departure_date, currency.upper())

        if not row or not row['last_fetched']:
            return False, None

        last_fetched = row['last_fetched']
        data = row['data']
        
        now_utc = datetime.now(pytz.UTC)
        is_near = departure_date <= (now_utc.date() + timedelta(days=1))
        is_empty = not data or not data.get('data') or len(data.get('data')) == 0
        
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
        # Czyści stare wpisy w cache cen z bazy danych
        async with db.get_connection() as conn:
            deleted_count = await conn.execute(f"""
                DELETE FROM flight_prices_cache
                WHERE 
                    (data->'data' != '[]'::jsonb AND (
                        (departure_date <= (CURRENT_DATE + 1) AND last_fetched_at < (NOW() - INTERVAL '{settings.price_cache_near_expiry_minutes} minute'))
                        OR
                        (departure_date > (CURRENT_DATE + 1) AND last_fetched_at < (NOW() - INTERVAL '{settings.price_cache_far_expiry_hours} hour'))
                    ))
                    OR
                    (data->'data' = '[]'::jsonb AND last_fetched_at < (NOW() - INTERVAL '{settings.price_cache_empty_ttl_hours} hour'))
            """)
            if deleted_count != "DELETE 0":
                debug_log(f"Wyczyszczono wygasły cache ofert: {deleted_count}")

    @staticmethod
    def _parse_offer_from_api(
        offer_data: Dict[str, Any],
        origin_city_code: str,
        destination_city_code: str,
        currency: str = settings.default_currency
    ) -> Optional[Dict[str, Any]]:
        # Konwertuje surowe dane z API zewnętrzne na format wewnętrzny
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
                debug_log(f"Błąd parsowania czasu wylotu: {e}")
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
                'link': offer_data.get('link'),
                'api_raw': offer_data
            }
        except Exception as e:
            logger.error(f"Błąd parsowania oferty: {str(e)}")
            return None

    @staticmethod
    async def _save_offers_to_db(conn, offers_data: List[Dict[str, Any]]) -> int:
        # Zapisuje przetworzone oferty do bazy danych (Upsert)
        saved_count = 0
        for offer_data in offers_data:
            try:
                await conn.execute("""
                    INSERT INTO flight_offers (
                        origin_city_code, destination_city_code,
                        origin_airport_code, destination_airport_code,
                        price, currency, airline_code, 
                        flight_number, departure_at, link, api_raw
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (origin_airport_code, destination_airport_code, departure_at, flight_number, price)
                    DO UPDATE SET
                        link = EXCLUDED.link,
                        api_raw = EXCLUDED.api_raw
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
                    json.dumps(offer_data['api_raw'], default=str)
                )
                saved_count += 1
            except Exception as e:
                logger.error(f"Błąd zapisu oferty: {str(e)}")
                raise
        return saved_count

    @staticmethod
    async def fetch_and_cache_offers(
        origin_city_code: str,
        destination_city_code: str,
        departure_date: date,
        currency: str = settings.default_currency
    ) -> Tuple[bool, Optional[datetime]]:
        # Pobiera świeże ceny z API i zapisuje je w cache (Redis + DB)
        await OfferService.cleanup_expired_cache()
        debug_log(f"Pobieranie ofert dla {origin_city_code}->{destination_city_code}")

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

        if cache.is_ready:
            date_iso = departure_date.isoformat()
            redis_key = f"prices:{origin_city_code}:{destination_city_code}:{date_iso}:{currency.upper()}"
            await cache.set(redis_key, {"last_fetched_at": now_utc.isoformat()}, ttl=ttl_sec)
        else:
            async with db.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO flight_prices_cache 
                    (origin_city_code, destination_city_code, departure_date, currency, last_fetched_at, data)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (origin_city_code, destination_city_code, departure_date, currency)
                    DO UPDATE SET
                        last_fetched_at = EXCLUDED.last_fetched_at,
                        data = EXCLUDED.data
                """, origin_city_code, destination_city_code, departure_date, currency.upper(), now_utc, json.dumps(api_response))

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
    ) -> Offers:
        # Pobiera oferty dla konkretnej trasy i czasu (Smart Match)
        departure_date = departure_at.date()
        
        if not origin_city_code or not destination_city_code:
            async with db.get_connection() as conn:
                if not origin_city_code:
                    origin_city_code = await conn.fetchval("SELECT city_code FROM airports WHERE code = $1", origin_airport_code)
                if not destination_city_code:
                    destination_city_code = await conn.fetchval("SELECT city_code FROM airports WHERE code = $1", destination_airport_code)

        if not origin_city_code or not destination_city_code:
            return Offers(data=[], count=0)

        cache_valid, last_fetched = await OfferService.is_cache_valid(origin_city_code, destination_city_code, departure_date, currency)

        if force_refresh or not cache_valid:
            success, last_fetched = await OfferService.fetch_and_cache_offers(origin_city_code, destination_city_code, departure_date, currency)

        if departure_at.tzinfo is not None:
            departure_at = departure_at.replace(tzinfo=None)

        async with db.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT
                    fo.id, fo.origin_city_code, fo.destination_city_code,
                    fo.origin_airport_code, fo.destination_airport_code,
                    fo.price, fo.currency, fo.airline_code, 
                    fo.flight_number, fo.departure_at, fo.link,
                    fo.created_at
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

            offers = [Offer(**dict(row)) for row in rows]
            return Offers(data=offers, count=len(offers), last_fetched_at=last_fetched)

    @staticmethod
    async def get_offers_for_city_pair(
        origin_city_code: str,
        destination_city_code: str,
        departure_date: date,
        currency: str = settings.default_currency,
        force_refresh: bool = False
    ) -> Offers:
        # Pobiera wszystkie dostępne oferty dla pary miast
        cache_valid, last_fetched = await OfferService.is_cache_valid(origin_city_code, destination_city_code, departure_date, currency)

        if force_refresh or not cache_valid:
            success, last_fetched = await OfferService.fetch_and_cache_offers(origin_city_code, destination_city_code, departure_date, currency)

        async with db.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT
                    fo.id, fo.origin_city_code, fo.destination_city_code,
                    fo.origin_airport_code, fo.destination_airport_code,
                    fo.price, fo.currency, fo.airline_code, fo.flight_number,
                    fo.departure_at, fo.link,
                    fo.created_at
                FROM flight_offers fo
                WHERE fo.origin_city_code = $1
                  AND fo.destination_city_code = $2
                  AND DATE(fo.departure_at) = $3
                  AND fo.currency = $4
                ORDER BY fo.price ASC
            """, origin_city_code, destination_city_code, departure_date, currency.upper())

            offers = [Offer(**dict(row)) for row in rows]
            return Offers(data=offers, count=len(offers), last_fetched_at=last_fetched)

# Globalna instancja serwisu ofert
offer_service = OfferService()
