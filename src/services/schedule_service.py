from typing import List, Optional, Dict, Any, Tuple, AsyncGenerator
from datetime import datetime, date, timedelta, time
from src.database import db
from src.models.schedule import Flight, Schedule, AirportScheduleCacheInfo
from src.services.api_client import aerodatabox_client
from src.config import settings
from src.cache import cache
import logging
import json
import pytz
import asyncio
import time as time_module

logger = logging.getLogger(__name__)

# Flaga debugowania: True włącza logi diagnostyczne dla serwisu rozkładów
DEBUG_SCHEDULE_SERVICE = settings.debug_flight_service

def debug_log(message: str):
    if DEBUG_SCHEDULE_SERVICE:
        logger.debug(message)


class ScheduleService:
    # Serwis zarządzający rozkładami lotów na lotniskach

    # Minimalny odstęp między zapytaniami do API (w sekundach)
    MIN_API_CALL_INTERVAL = settings.aerodatabox_api_call_interval

    # Czas ostatniego udanego zapytania do API (do throttling-u)
    _last_api_call_time = 0.0

    # Lokalna blokada używana gdy Redis nie jest dostępny
    _local_api_call_locks: Dict[str, asyncio.Lock] = {}
    
    # [v24.90]: Globalny strażnik odstępu między zapytaniami (Throttle Mutex)
    _api_throttle_lock: Optional[asyncio.Lock] = None

    @classmethod
    def _get_local_lock(cls, name: str = "default") -> asyncio.Lock:
        # Mechanizm synchronizacji procesów przy braku serwera Redis
        if name not in cls._local_api_call_locks:
            cls._local_api_call_locks[name] = asyncio.Lock()
        return cls._local_api_call_locks[name]
    
    @classmethod
    def _get_throttle_lock(cls) -> asyncio.Lock:
        if cls._api_throttle_lock is None:
            cls._api_throttle_lock = asyncio.Lock()
        return cls._api_throttle_lock

    @staticmethod
    def _get_chunk_start(dt: datetime) -> datetime:
        # Wyznacza początek 12-godzinnego okna czasowego (00:00 lub 12:00) dla stabilnego cache'u
        hour = 12 if dt.time() >= time(12, 0) else 0
        return dt.replace(hour=hour, minute=0, second=0, microsecond=0)

    @staticmethod
    def _get_chunks_for_range(from_dt: datetime, to_dt: datetime, local_today: date) -> list:
        # Generuje listę punktów startowych dla 12-godzinnych paczek danych w danym zakresie
        _ = local_today
        chunks = []
        current = ScheduleService._get_chunk_start(from_dt)
        while current < to_dt:
            chunks.append(current)
            current += timedelta(hours=12)
        return chunks

    @staticmethod
    async def _get_airport_tz(airport_code: str):
        # Pobiera strefę czasową lotniska z bazy danych
        async with db.get_connection() as conn:
            timezone_str = await conn.fetchval(
                "SELECT time_zone FROM airports WHERE code = $1", airport_code
            )
        if not timezone_str:
            return pytz.UTC
        try:
            return pytz.timezone(timezone_str)
        except Exception:
            return pytz.UTC

    @staticmethod
    async def find_cache_for_datetime(
        airport_code: str,
        from_local_datetime: datetime,
        direction: str = settings.default_flight_direction
    ) -> Optional[Dict]:
        # Szuka ważnego wpisu w cache'u dla konkretnego okna czasowego (Hybrid Cache)
        from_iso = from_local_datetime.isoformat()
        redis_key = f"schedules:{airport_code}:{direction}:{from_iso}"
        
        # 1. Próbujemy najpierw w szybkim cache'u Redis
        if cache.is_ready:
            redis_data = await cache.get(redis_key)
            if redis_data:
                debug_log(f"Redis Cache HIT for {airport_code} @ {from_iso}")
                redis_data['last_fetched_at'] = datetime.fromisoformat(redis_data['last_fetched_at'])
                redis_data['fetch_from_local'] = datetime.fromisoformat(redis_data['fetch_from_local'])
                redis_data['fetch_to_local'] = datetime.fromisoformat(redis_data['fetch_to_local'])
                return redis_data
            
            # Jeśli Redis działa, ale nie ma klucza, to nie szukamy w SQL
            return None

        # 2. Rezerwowo sprawdzamy w bazie PostgreSQL (tylko gdy Redis leży)
        now_utc = datetime.now(pytz.UTC)
        airport_tz = await ScheduleService._get_airport_tz(airport_code)
        local_now = now_utc.astimezone(airport_tz).replace(tzinfo=None)
        
        is_near = from_local_datetime <= (local_now + timedelta(hours=24))
        
        if is_near:
            interval = f"{settings.flight_cache_near_expiry_minutes} minute"
        else:
            interval = f"{settings.flight_cache_far_expiry_hours} hour"

        async with db.get_connection() as conn:
            row = await conn.fetchrow(f"""
                SELECT id, last_fetched_at, fetch_from_local, fetch_to_local, data
                FROM airport_schedules_cache
                WHERE airport_code = $1
                  AND direction = $2
                  AND fetch_from_local <= $3
                  AND fetch_to_local >= $3
                  AND (
                    ((data->'departures' != '[]'::jsonb OR data->'arrivals' != '[]'::jsonb) AND last_fetched_at > (NOW() - INTERVAL '{interval}'))
                    OR
                    ((data->'departures' = '[]'::jsonb AND data->'arrivals' = '[]'::jsonb) AND last_fetched_at > (NOW() - INTERVAL '{settings.flight_cache_empty_expiry_days} day'))
                  )
                ORDER BY fetch_from_local DESC
                LIMIT 1
            """, airport_code, direction, from_local_datetime)

            if row:
                debug_log(f"SQL Cache HIT for {airport_code} @ {from_iso}")
                return dict(row)
            return None

    @staticmethod
    async def cleanup_expired_cache():
        # Usuwa przedawnione wpisy z cache'u rozkładów na podstawie reguł TTL
        async with db.get_connection() as conn:
            deleted_count = await conn.execute(f"""
                DELETE FROM airport_schedules_cache
                WHERE 
                    ((data->'departures' != '[]'::jsonb OR data->'arrivals' != '[]'::jsonb) AND (
                        (fetch_from_local <= (NOW() + INTERVAL '24 hour') AND last_fetched_at < (NOW() - INTERVAL '{settings.flight_cache_near_expiry_minutes} minute'))
                        OR
                        (fetch_from_local > (NOW() + INTERVAL '24 hour') AND last_fetched_at < (NOW() - INTERVAL '{settings.flight_cache_far_expiry_hours} hour'))
                    ))
                    OR
                    ((data->'departures' = '[]'::jsonb AND data->'arrivals' = '[]'::jsonb) AND last_fetched_at < (NOW() - INTERVAL '{settings.flight_cache_empty_expiry_days} day'))
            """)
            if deleted_count != "DELETE 0":
                debug_log(f"Cleaned up expired schedule cache: {deleted_count}")

    @staticmethod
    async def get_cache_info(
        airport_code: str,
        from_local_datetime: datetime,
        direction: str = settings.default_flight_direction
    ) -> AirportScheduleCacheInfo:
        # Zwraca ujednolicone informacje o stanie cache dla konkretnego okna
        from_iso = from_local_datetime.isoformat()
        redis_key = f"schedules:{airport_code}:{direction}:{from_iso}"

        if cache.is_ready:
            redis_data = await cache.get(redis_key)
            if redis_data:
                return AirportScheduleCacheInfo(
                    airport_code=airport_code,
                    direction=direction,
                    has_cache=True,
                    last_fetched_at=datetime.fromisoformat(redis_data['last_fetched_at']),
                    records_count=0 if redis_data.get('is_empty') else None
                )
            
            # Redis działa i nie ma danych zwracamy brak cache'u
            return AirportScheduleCacheInfo(
                airport_code=airport_code,
                direction=direction,
                has_cache=False
            )

        # Rezerwowe sprawdzanie w SQL (gdy Redis nie działa)
        async with db.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT last_fetched_at, fetch_from_local, fetch_to_local
                FROM airport_schedules_cache
                WHERE airport_code = $1
                  AND direction = $2
                  AND fetch_from_local <= $3
                  AND fetch_to_local >= $3
                ORDER BY fetch_from_local DESC
                LIMIT 1
            """, airport_code, direction, from_local_datetime)

            if row:
                return AirportScheduleCacheInfo(
                    airport_code=airport_code,
                    direction=direction,
                    has_cache=True,
                    last_fetched_at=row['last_fetched_at'],
                    records_count=None
                )

            return AirportScheduleCacheInfo(
                airport_code=airport_code,
                direction=direction,
                has_cache=False
            )

    @staticmethod
    def _parse_flight_from_api(
        flight_data: Dict[str, Any],
        is_departure: bool
    ) -> Optional[Dict[str, Any]]:
        # Mapuje surowe dane o locie z API AeroDataBox na nasz wewnętrzny format
        try:
            flight_number = flight_data.get('number')
            if not flight_number:
                return None

            airline = flight_data.get('airline', {})
            airline_code = airline.get('iata')
            airline_name = airline.get('name')

            def parse_time_dict(time_obj):
                if not time_obj:
                    return None, None
                utc_str = time_obj.get('utc')
                local_str = time_obj.get('local')
                try:
                    utc = datetime.fromisoformat(utc_str.replace('Z', '+00:00').replace(' ', 'T')) if utc_str else None
                    if utc:
                        utc = utc.replace(second=0, microsecond=0)
                    if local_str:
                        local_with_tz = datetime.fromisoformat(local_str.replace(' ', 'T'))
                        local = local_with_tz.replace(tzinfo=None, second=0, microsecond=0)
                    else:
                        local = None
                    return utc, local
                except Exception as e:
                    debug_log(f"Error parsing time: {e}")
                    return None, None

            dep_obj = flight_data.get('departure', {})
            arr_obj = flight_data.get('arrival', {})

            dep_sched_utc, dep_sched_local = parse_time_dict(dep_obj.get('scheduledTime'))
            arr_sched_utc, arr_sched_local = parse_time_dict(arr_obj.get('scheduledTime'))

            if is_departure:
                arr_airport = arr_obj.get('airport', {})
                dest_airport_code = arr_airport.get('iata') or arr_airport.get('icao')
                if not dep_sched_utc or not dest_airport_code:
                    return None
                return {
                    'flight_number': flight_number,
                    'airline_code': airline_code,
                    'airline_name': airline_name,
                    'destination_airport_code': dest_airport_code,
                    'scheduled_departure_utc': dep_sched_utc,
                    'scheduled_departure_local': dep_sched_local,
                    'scheduled_arrival_utc': arr_sched_utc,
                    'scheduled_arrival_local': arr_sched_local,
                    'departure_terminal': dep_obj.get('terminal'),
                    'departure_gate': dep_obj.get('gate')
                }
            else:
                dep_airport = dep_obj.get('airport', {})
                origin_airport_code = dep_airport.get('iata') or dep_airport.get('icao')
                if not arr_sched_utc or not origin_airport_code:
                    return None
                return {
                    'flight_number': flight_number,
                    'airline_code': airline_code,
                    'airline_name': airline_name,
                    'origin_airport_code': origin_airport_code,
                    'scheduled_departure_utc': dep_sched_utc,
                    'scheduled_departure_local': dep_sched_local,
                    'scheduled_arrival_utc': arr_sched_utc,
                    'scheduled_arrival_local': arr_sched_local,
                    'departure_terminal': dep_obj.get('terminal'),
                    'departure_gate': dep_obj.get('gate')
                }
        except Exception as e:
            logger.error(f"Error parsing schedule: {str(e)}")
            return None

    @staticmethod
    async def _save_flights_to_db(conn, flights_data: List[Dict[str, Any]]) -> int:
        # Zapisuje przetworzone dane o lotach do bazy
        saved_count = 0
        for flight_data in flights_data:
            try:
                # Sprawdzenie czy lotniska istnieją w naszej bazie przed zapisem lotu
                if flight_data.get('origin_airport_code'):
                    origin_exists = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM airports WHERE code = $1)",
                        flight_data['origin_airport_code']
                    )
                    if not origin_exists: continue

                if flight_data.get('destination_airport_code'):
                    dest_exists = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM airports WHERE code = $1)",
                        flight_data['destination_airport_code']
                    )
                    if not dest_exists: continue

                await conn.execute("""
                    INSERT INTO flights (
                        flight_number, airline_code, airline_name, 
                        origin_airport_code, destination_airport_code,
                        scheduled_departure_utc, scheduled_departure_local,
                        scheduled_arrival_utc, scheduled_arrival_local,
                        departure_terminal, departure_gate, api_raw
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (flight_number, scheduled_departure_utc, origin_airport_code, destination_airport_code)
                    DO UPDATE SET
                        airline_name = EXCLUDED.airline_name,
                        scheduled_arrival_utc = EXCLUDED.scheduled_arrival_utc,
                        scheduled_arrival_local = EXCLUDED.scheduled_arrival_local,
                        departure_gate = EXCLUDED.departure_gate,
                        api_raw = EXCLUDED.api_raw
                """,
                    flight_data['flight_number'],
                    flight_data['airline_code'],
                    flight_data['airline_name'],
                    flight_data['origin_airport_code'],
                    flight_data['destination_airport_code'],
                    flight_data['scheduled_departure_utc'],
                    flight_data['scheduled_departure_local'],
                    flight_data['scheduled_arrival_utc'],
                    flight_data['scheduled_arrival_local'],
                    flight_data['departure_terminal'],
                    flight_data['departure_gate'],
                    json.dumps(flight_data, default=str)
                )
                saved_count += 1
            except Exception as e:
                logger.error(f"Error saving schedule: {str(e)}")
                raise
        return saved_count

    @staticmethod
    async def fetch_and_cache_schedule_chunk(
        airport_code: str,
        from_local_datetime: Optional[datetime] = None,
        direction: str = settings.default_flight_direction
    ) -> Tuple[bool, Optional[datetime], Optional[datetime]]:
        # Pobiera loty z API dla 12-godzinnego okna i zapisuje je w cache'u (Redis + SQL)
        debug_log(f"Pobieranie lotów dla {airport_code} od {from_local_datetime}")
        await ScheduleService.cleanup_expired_cache()

        airport_tz = await ScheduleService._get_airport_tz(airport_code)
        if from_local_datetime is not None:
            from_time = from_local_datetime
        else:
            utc_now = datetime.now(pytz.UTC)
            local_now = utc_now.astimezone(airport_tz)
            from_time = local_now.replace(tzinfo=None)

        to_time = from_time + timedelta(hours=settings.aerodatabox_window_hours) - timedelta(minutes=1)
        from_local_str = from_time.strftime("%Y-%m-%dT%H:%M")
        to_local_str = to_time.strftime("%Y-%m-%dT%H:%M")

        # [v24.90]: Blokada specyficzna dla lotniska (per-airport lock), aby zapobiec duplikatom
        # Nie blokuje ona innych lotnisk, jedynie inne requesty o TEN SAM fragment tego lotniska.
        airport_lock_name = f"aerodatabox_api:{airport_code}:{from_time.isoformat()}"
        redis_airport_lock = cache.get_lock(airport_lock_name, timeout=60)
        airport_lock = redis_airport_lock if redis_airport_lock else ScheduleService._get_local_lock(airport_lock_name)

        async with airport_lock:
            # Sprawdzamy cache ponownie wewnątrz blokady lotniska
            cached_again = await ScheduleService.find_cache_for_datetime(airport_code, from_time, direction)
            if cached_again:
                return True, cached_again['last_fetched_at'], None

            # [v24.90]: Globalny strażnik odstępu (Throttle Mutex)
            # Trzymamy go tylko przez moment wyliczania i czekania na "slot" czasowy.
            throttle_lock = ScheduleService._get_throttle_lock()
            async with throttle_lock:
                time_since_last_call = time_module.time() - ScheduleService._last_api_call_time
                if time_since_last_call < ScheduleService.MIN_API_CALL_INTERVAL:
                    sleep_time = ScheduleService.MIN_API_CALL_INTERVAL - time_since_last_call
                    await asyncio.sleep(sleep_time)
                
                # Rezerwujemy slot i aktualizujemy czas
                ScheduleService._last_api_call_time = time_module.time()
                # LOCK ODSTĘPU ZWALNIANY TUTAJ (koniec bloku async with)
            
            # WŁAŚCIWE ZAPYTANIE API (wykonywane poza globalną blokadą, ale wewnątrz blokady lotniska)
            # Dzięki temu wiele lotnisk może "wisieć" na połączeniach HTTP naraz.
            api_response = await aerodatabox_client.get_airport_departures(
                airport_code=airport_code,
                from_local=from_local_str,
                to_local=to_local_str,
                direction=direction,
                with_leg=True
            )

        if not api_response:
            return False, None, None

        flights_data = []
        departures = api_response.get('departures', [])
        for entry in departures:
            parsed = ScheduleService._parse_flight_from_api(entry, is_departure=True)
            if parsed:
                parsed['origin_airport_code'] = airport_code
                flights_data.append(parsed)

        if flights_data:
            async with db.get_connection() as conn:
                await ScheduleService._save_flights_to_db(conn, flights_data)

        now_utc = datetime.now(pytz.UTC)
        local_now = datetime.now(pytz.UTC).astimezone(airport_tz).replace(tzinfo=None)
        is_near = from_time <= (local_now + timedelta(hours=24))
        is_empty = len(departures) == 0
        
        if is_empty:
            ttl_sec = settings.flight_cache_empty_ttl_sec
        elif is_near:
            ttl_sec = int(settings.flight_cache_near_expiry_minutes * 60)
        else:
            ttl_sec = int(settings.flight_cache_far_expiry_hours * 3600)

        # Odświeżenie szybkiego cache'u w Redisie
        if cache.is_ready:
            from_iso = from_time.isoformat()
            redis_key = f"schedules:{airport_code}:{direction}:{from_iso}"
            redis_value = {
                "last_fetched_at": now_utc.isoformat(),
                "fetch_from_local": from_time.isoformat(),
                "fetch_to_local": to_time.isoformat()
            }
            await cache.set(redis_key, redis_value, ttl=ttl_sec)
        else:
            # Rezerwowy zapis do SQL
            async with db.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO airport_schedules_cache 
                    (airport_code, direction, fetch_from_local, fetch_to_local, last_fetched_at, data)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (airport_code, direction, fetch_from_local) 
                    DO UPDATE SET 
                        last_fetched_at = EXCLUDED.last_fetched_at,
                        data = EXCLUDED.data,
                        fetch_to_local = EXCLUDED.fetch_to_local
                """, airport_code, direction, from_time, to_time, now_utc, json.dumps(api_response))

        return True, now_utc, to_time

    @staticmethod
    async def stream_schedule_from_airport(
        airport_code: str,
        from_local_datetime: Optional[datetime] = None,
        limit: int = 200,
        force_refresh: bool = False,
        to_local_datetime: Optional[datetime] = None
    ) -> AsyncGenerator[Schedule, None]:
        # Generator asynchroniczny zwracający rozkład lotów lotniska w 12-godzinnych paczkach
        direction = settings.default_flight_direction
        if from_local_datetime is None:
            from_local_datetime = datetime.utcnow().replace(second=0, microsecond=0)

        airport_tz = await ScheduleService._get_airport_tz(airport_code)
        utc_now = datetime.now(pytz.UTC)
        local_now = utc_now.astimezone(airport_tz)
        local_today = local_now.date()

        if to_local_datetime is not None:
            end_of_query = to_local_datetime
        else:
            end_of_query = datetime.combine(from_local_datetime.date(), time.max)

        chunks_needed = ScheduleService._get_chunks_for_range(from_local_datetime, end_of_query, local_today)
        
        # [v24.85]: Równoległe "rozgrzewanie" (warming) cache'u dla wszystkich potrzebnych paczek
        # Pozwala to uniknąć sekwencyjnego czekania 1.5s na każdą paczkę z osobna.
        async def warm_chunk(chunk_start):
            info = await ScheduleService.find_cache_for_datetime(airport_code, chunk_start, direction)
            if not info or force_refresh:
                await ScheduleService.fetch_and_cache_schedule_chunk(airport_code, chunk_start, direction)

        try:
            # Uruchamiamy zadania rozgrzewania w tle
            warming_tasks = [asyncio.create_task(warm_chunk(c)) for c in chunks_needed]

            for i, chunk_start in enumerate(chunks_needed):
                chunk_end = chunk_start + timedelta(hours=12)
                
                # Czekamy na zakończenie rozgrzewania tej konkretnej paczki (mogło się już zakończyć w tle)
                await warming_tasks[i]
                
                # Pobieramy aktualne info o cache po operacji warming
                info = await ScheduleService.find_cache_for_datetime(airport_code, chunk_start, direction)
                
                query_start = from_local_datetime if i == 0 else chunk_start
                query_end   = min(chunk_end, end_of_query)

                async with db.get_connection() as conn:
                    # Pobieranie paczki lotów z bazy dla aktualnego okna czasowego
                    rows = await conn.fetch("""
                        SELECT
                            flight_number, airline_code, airline_name,
                            origin_airport_code, destination_airport_code,
                            scheduled_departure_utc, scheduled_departure_local,
                            scheduled_arrival_utc, scheduled_arrival_local,
                            departure_terminal, departure_gate
                        FROM flights
                        WHERE origin_airport_code = $1
                          AND scheduled_departure_local >= $2
                          AND scheduled_departure_local <= $3
                        ORDER BY scheduled_departure_local ASC
                        LIMIT $4
                    """, airport_code, query_start, query_end, limit)

                    total_count = await conn.fetchval("""
                        SELECT COUNT(*)
                        FROM flights
                        WHERE origin_airport_code = $1
                          AND scheduled_departure_local >= $2
                          AND scheduled_departure_local <= $3
                    """, airport_code, query_start, query_end)

                flights = [Flight(**dict(row)) for row in rows]
                yield Schedule(
                    data=flights,
                    count=total_count or 0,
                    last_fetched_at=info['last_fetched_at'] if info else None,
                    range_end_datetime=query_end.isoformat()
                )
        except asyncio.CancelledError:
            # [v24.85]: Przerwanie połączenia przez klienta (abort) -> zatrzymujemy oczekiwanie na API
            debug_log(f"Stream for {airport_code} cancelled by client. Stopping fetches.")
            # Próbujemy przerwać zadania, które jeszcze nie ruszyły
            for task in warming_tasks:
                if not task.done():
                    task.cancel()
            raise

    @staticmethod
    async def get_schedule_from_airport(
        airport_code: str,
        from_local_datetime: Optional[datetime] = None,
        limit: int = 200,
        force_refresh: bool = False,
        to_local_datetime: Optional[datetime] = None,
    ) -> Schedule:
        # Skleja wszystkie mniejsze paczki lotów w jeden pełny rozkład dla danego zakresu
        flights = []
        last_fetched_at = None
        range_end_datetime = None
        total_count = 0

        async for batch in ScheduleService.stream_schedule_from_airport(
            airport_code=airport_code,
            from_local_datetime=from_local_datetime,
            limit=limit,
            force_refresh=force_refresh,
            to_local_datetime=to_local_datetime
        ):
            flights.extend(batch.data)
            total_count += batch.count
            if batch.last_fetched_at:
                last_fetched_at = batch.last_fetched_at
            range_end_datetime = batch.range_end_datetime

        return Schedule(
            data=flights,
            count=total_count,
            last_fetched_at=last_fetched_at,
            range_end_datetime=range_end_datetime
        )

# Globalny obiekt serwisu rozkładów lotów
schedule_service = ScheduleService()
