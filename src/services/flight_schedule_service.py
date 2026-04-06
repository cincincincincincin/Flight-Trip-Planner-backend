from typing import List, Optional, Dict, Any, Tuple, AsyncGenerator
from datetime import datetime, date, timedelta, time
from src.database import db
from src.models.flight import Flight, FlightsResponse, CacheInfo, AirportSchedulesCacheInfo
from src.services.api_client import aerodatabox_client
from src.config import settings
import logging
import json
import pytz
import asyncio
import time as time_module

logger = logging.getLogger(__name__)

# Flaga debugowania: ustawienie na False wyłącza logi diagnostyczne serwisu
DEBUG_FLIGHT_SERVICE = settings.debug_flight_service

def debug_log(message: str):
    if DEBUG_FLIGHT_SERVICE:
        logger.debug(message)


class FlightScheduleService:
    # Serwis zarządzający harmonogramami lotów pobieranymi z zewnętrznego API AeroDataBox

    # Czas wygasania pamięci podręcznej harmonogramów wyrażony w godzinach
    CACHE_EXPIRY_HOURS = settings.flight_cache_expiry_hours

    # Minimalny odstęp czasu między zapytaniami do API AeroDataBox (sekundy)
    MIN_API_CALL_INTERVAL = settings.aerodatabox_api_call_interval

    # Znacznik czasu ostatniego pomyślnego zapytania
    _last_api_call_time = 0.0

    # Blokada zapewniająca sekwencyjne wywołania API i zapobiegająca wyścigom
    _api_call_lock: Optional[asyncio.Lock] = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        # Zwraca lub inicjalizuje blokadę dostępu do zasobów API
        if cls._api_call_lock is None:
            cls._api_call_lock = asyncio.Lock()
        return cls._api_call_lock

    @staticmethod
    def _get_chunk_start(dt: datetime) -> datetime:
        # Wyznacza początek 12-godzinnego okna czasowego (00:00 lub 12:00) dla danej daty
        hour = 12 if dt.time() >= time(12, 0) else 0
        return dt.replace(hour=hour, minute=0, second=0, microsecond=0)

    @staticmethod
    def _get_chunks_for_range(from_dt: datetime, to_dt: datetime, local_today: date) -> list:
        # Generuje listę znaczników czasu dla 12-godzinnych paczek danych pokrywających zadany zakres
        # Pętla iteruje od okna startowego do momentu osiągnięcia czasu końcowego
        _ = local_today
        chunks = []
        current = FlightScheduleService._get_chunk_start(from_dt)
        while current < to_dt:
            chunks.append(current)
            current += timedelta(hours=12)
        return chunks

    @staticmethod
    async def _get_airport_tz(airport_code: str):
        # Pobiera strefę czasową lotniska z bazy danych, domyślnie zwraca UTC
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
        # Wyszukuje ważny wpis w pamięci podręcznej dla konkretnego okna czasowego i lotniska
        async with db.get_connection() as conn:
            row = await conn.fetchrow(f"""
                SELECT id, last_fetched_at, fetch_from_local, fetch_to_local
                FROM airport_schedules_cache
                WHERE airport_code = $1
                  AND direction = $2
                  AND fetch_from_local <= $3
                  AND fetch_to_local >= $3
                  AND last_fetched_at > (NOW() - INTERVAL '{settings.flight_cache_expiry_hours} hour')
                ORDER BY fetch_from_local DESC
                LIMIT 1
            """, airport_code, direction, from_local_datetime)

            if row:
                return dict(row)
            return None

    @staticmethod
    async def get_cache_info(
        airport_code: str,
        search_date: date,
        direction: str = settings.default_flight_direction
    ) -> CacheInfo:
        # Zwraca metadane dotyczące stanu pamięci podręcznej dla danego lotniska i dnia
        async with db.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT last_fetched_at, fetch_from_local, fetch_to_local
                FROM airport_schedules_cache
                WHERE airport_code = $1
                  AND direction = $2
                  AND DATE(fetch_from_local) = $3
                ORDER BY fetch_from_local DESC
                LIMIT 1
            """, airport_code, direction, search_date)

            if row:
                return CacheInfo(
                    has_cache=True,
                    last_fetched_at=row['last_fetched_at'],
                    records_count=None
                )

            return CacheInfo(has_cache=False)

    @staticmethod
    def _parse_flight_from_api(
        flight_data: Dict[str, Any],
        search_date: date,
        is_departure: bool
    ) -> Optional[Dict[str, Any]]:
        # Mapuje dane lotu z odpowiedzi AeroDataBox na ustandaryzowany słownik
        try:
            flight_number = flight_data.get('number')
            if not flight_number:
                debug_log(f"Skipping flight: no flight number")
                return None

            airline = flight_data.get('airline', {})
            airline_code = airline.get('iata')
            airline_name = airline.get('name')

            def parse_time_dict(time_obj):
                # Pomocnicza funkcja parsująca daty i czasy z formatu ISO na obiekty datetime
                if not time_obj:
                    return None, None
                utc_str = time_obj.get('utc')
                local_str = time_obj.get('local')
                try:
                    utc = datetime.fromisoformat(utc_str.replace('Z', '+00:00').replace(' ', 'T')) if utc_str else None
                    if local_str:
                        local_with_tz = datetime.fromisoformat(local_str.replace(' ', 'T'))
                        local = local_with_tz.replace(tzinfo=None)
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
                    debug_log(f"Skipping departure {flight_number}: missing departure time or destination")
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
                    'departure_gate': dep_obj.get('gate'),
                    'search_date': search_date
                }
            else:
                dep_airport = dep_obj.get('airport', {})
                origin_airport_code = dep_airport.get('iata') or dep_airport.get('icao')

                if not arr_sched_utc or not origin_airport_code:
                    debug_log(f"Skipping arrival {flight_number}: missing arrival time or origin")
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
                    'departure_gate': dep_obj.get('gate'),
                    'search_date': search_date
                }
        except Exception as e:
            logger.error(f"Error parsing flight: {str(e)}")
            return None

    @staticmethod
    async def _save_flights_to_db(conn, flights_data: List[Dict[str, Any]]) -> int:
        # Zapisuje sparsowane loty do bazy danych przy użyciu aktywnego połączenia
        # Metoda realizuje operację upsert oraz walidację kluczy obcych (lotniska, linie)
        saved_count = 0
        skipped_count = 0
        for flight_data in flights_data:
            try:
                # Weryfikacja istnienia lotnisk i linii lotniczych przed próbą zapisu
                if flight_data.get('origin_airport_code'):
                    origin_exists = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM airports WHERE code = $1)",
                        flight_data['origin_airport_code']
                    )
                    if not origin_exists:
                        debug_log(f"Skipping flight {flight_data.get('flight_number')}: origin airport {flight_data['origin_airport_code']} not in database")
                        skipped_count += 1
                        continue

                if flight_data.get('destination_airport_code'):
                    dest_exists = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM airports WHERE code = $1)",
                        flight_data['destination_airport_code']
                    )
                    if not dest_exists:
                        debug_log(f"Skipping flight {flight_data.get('flight_number')}: destination airport {flight_data['destination_airport_code']} not in database")
                        skipped_count += 1
                        continue

                if flight_data.get('airline_code') and flight_data.get('airline_name'):
                    # Mechanizm JIT: Automatyczne dodawanie nieznanej linii do bazy danych
                    await conn.execute("""
                        INSERT INTO airlines (code, name)
                        VALUES ($1, $2)
                        ON CONFLICT (code) DO NOTHING
                    """, flight_data['airline_code'], flight_data['airline_name'])

                # Wykonanie zapytania INSERT z klauzulą ON CONFLICT dla aktualizacji istniejących rekordów
                await conn.execute("""
                    INSERT INTO flights (
                        flight_number, airline_code, origin_airport_code, destination_airport_code,
                        scheduled_departure_utc, scheduled_departure_local,
                        scheduled_arrival_utc, scheduled_arrival_local,
                        departure_terminal, departure_gate,
                        search_date ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (flight_number, scheduled_departure_utc, origin_airport_code, destination_airport_code)
                    DO UPDATE SET
                        scheduled_arrival_utc = EXCLUDED.scheduled_arrival_utc,
                        scheduled_arrival_local = EXCLUDED.scheduled_arrival_local,
                        departure_gate = EXCLUDED.departure_gate
                """,
                    flight_data['flight_number'],
                    flight_data['airline_code'],
                    flight_data['origin_airport_code'],
                    flight_data['destination_airport_code'],
                    flight_data['scheduled_departure_utc'],
                    flight_data['scheduled_departure_local'],
                    flight_data['scheduled_arrival_utc'],
                    flight_data['scheduled_arrival_local'],
                    flight_data['departure_terminal'],
                    flight_data['departure_gate'],
                    flight_data['search_date']
                )
                saved_count += 1
            except Exception as e:
                logger.error(f"Error saving flight {flight_data.get('flight_number')}: {str(e)}")
                raise

        debug_log(f"Saved {saved_count} flights to database, skipped {skipped_count} flights with missing airports/airlines")
        return saved_count

    @staticmethod
    async def fetch_and_cache_schedules(
        airport_code: str,
        from_local_datetime: Optional[datetime] = None,
        direction: str = settings.default_flight_direction
    ) -> Tuple[bool, Optional[datetime], Optional[datetime]]:
        # Pobiera harmonogramy z API dla 12-godzinnego okna czasowego i zapisuje je w cache.
        # Metoda orkiestruje cały proces: od sprawdzenia blokad API po atomowy zapis w DB.
        debug_log(f"Fetching schedules for {airport_code} from {from_local_datetime} ({direction})")

        airport_tz = await FlightScheduleService._get_airport_tz(airport_code)

        # Wyznaczenie punktu startowego zapytania (bieżący czas na lotnisku lub zadany parametr)
        if from_local_datetime is not None:
            from_time = from_local_datetime
        else:
            utc_now = datetime.now(pytz.UTC)
            local_now = utc_now.astimezone(airport_tz)
            from_time = local_now.replace(tzinfo=None)

        # Określenie zakresu czasowego (AeroDataBox obsługuje maksymalnie 12 godzin)
        to_time = from_time + timedelta(hours=settings.aerodatabox_window_hours) - timedelta(minutes=1)
        search_date = from_time.date()

        from_local_str = from_time.strftime("%Y-%m-%dT%H:%M")
        to_local_str = to_time.strftime("%Y-%m-%dT%H:%M")

        # Synchronizacja wywołań API przy użyciu blokady asynchronicznej
        lock = FlightScheduleService._get_lock()
        async with lock:
            # Kontrola częstotliwości zapytań (Rate Limiting na poziomie serwisu)
            time_since_last_call = time_module.time() - FlightScheduleService._last_api_call_time
            if time_since_last_call < FlightScheduleService.MIN_API_CALL_INTERVAL:
                sleep_time = FlightScheduleService.MIN_API_CALL_INTERVAL - time_since_last_call
                debug_log(f"Rate limiting: sleeping for {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)

            # Podwójne sprawdzenie cache (Double-Checked Locking): upewnienie się że inny proces
            # nie uzupełnił danych w trakcie oczekiwania na blokadę.
            cached_again = await FlightScheduleService.find_cache_for_datetime(
                airport_code, from_time, direction
            )
            if cached_again:
                debug_log(f"Cache hit after lock for {airport_code} from {from_time} — skipping API call")
                return True, cached_again['last_fetched_at'], None

            # Aktualizacja znacznika czasu przed wywołaniem API RapidAPI/AeroDataBox
            FlightScheduleService._last_api_call_time = time_module.time()

            api_response = await aerodatabox_client.get_airport_departures(
                airport_code=airport_code,
                from_local=from_local_str,
                to_local=to_local_str,
                direction=direction,
                with_leg=True
            )

        if not api_response:
            logger.error(f"Failed to fetch schedules from API for {airport_code}")
            return False, None, None

        # Przetworzenie otrzymanych danych przed otwarciem transakcji bazy danych
        flights_data = []
        departures = api_response.get('departures', [])
        arrivals = api_response.get('arrivals', [])

        for flight in departures:
            parsed = FlightScheduleService._parse_flight_from_api(flight, search_date, is_departure=True)
            if parsed:
                parsed['origin_airport_code'] = airport_code
                flights_data.append(parsed)

        for flight in arrivals:
            parsed = FlightScheduleService._parse_flight_from_api(flight, search_date, is_departure=False)
            if parsed:
                parsed['destination_airport_code'] = airport_code
                flights_data.append(parsed)

        # Atomowy zapis: aktualizacja wpisu w cache oraz wstawienie lotów w jednej transakcji
        async with db.get_connection() as conn:
            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO airport_schedules_cache (airport_code, direction, data, fetch_from_local, fetch_to_local)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (airport_code, direction, fetch_from_local)
                    DO UPDATE SET
                        last_fetched_at = NOW(),
                        data = EXCLUDED.data,
                        fetch_to_local = EXCLUDED.fetch_to_local
                """, airport_code, direction, json.dumps(api_response), from_time, to_time)

                await FlightScheduleService._save_flights_to_db(conn, flights_data)

        return True, datetime.now(), to_time

    @staticmethod
    async def stream_flights_from_airport(
        airport_code: str,
        from_local_datetime: Optional[datetime] = None,
        search_date: Optional[date] = None,
        limit: int = 200,
        force_refresh: bool = False,
        to_local_datetime: Optional[datetime] = None,
    ) -> AsyncGenerator[FlightsResponse, None]:
        # Generator asynchroniczny zwracający loty z danego lotniska w formie przyrostowej (paczki 12h).
        # Umożliwia frontendowi płynne wyświetlanie danych bez oczekiwania na pełny wynik zapytania.
        direction = settings.default_flight_direction

        # Wyznaczenie punktu startowego na podstawie daty wyszukiwania lub czasu UTC
        if from_local_datetime is None:
            if search_date is not None:
                from_local_datetime = datetime.combine(search_date, time.min)
            else:
                from_local_datetime = datetime.utcnow().replace(second=0, microsecond=0)

        # Pobranie strefy czasowej lotniska dla poprawnej kalkulacji lokalnego czasu operacyjnego
        airport_tz = await FlightScheduleService._get_airport_tz(airport_code)
        utc_now = datetime.now(pytz.UTC)
        local_now = utc_now.astimezone(airport_tz)
        local_today = local_now.date()

        # Określenie momentu zakończenia zapytania (domyślnie koniec bieżącego dnia lokalnego)
        if to_local_datetime is not None:
            end_of_query = to_local_datetime
        else:
            end_of_query = datetime.combine(from_local_datetime.date(), time.max)

        # Podział zakresu na 12-godzinne okna czasowe obsługiwane przez API
        chunks_needed = FlightScheduleService._get_chunks_for_range(
            from_local_datetime, end_of_query, local_today
        )
        for i, chunk_start in enumerate(chunks_needed):
            # Przetwarzanie każdej 12-godzinnej paczki danych z osobna
            chunk_end = chunk_start + timedelta(hours=12)
            
            if force_refresh:
                await FlightScheduleService.fetch_and_cache_schedules(
                    airport_code, chunk_start, direction
                )
                info = await FlightScheduleService.find_cache_for_datetime(
                    airport_code, chunk_start, direction
                )
            else:
                info = await FlightScheduleService.find_cache_for_datetime(
                    airport_code, chunk_start, direction
                )
                if not info:
                    await FlightScheduleService.fetch_and_cache_schedules(
                        airport_code, chunk_start, direction
                    )
                    info = await FlightScheduleService.find_cache_for_datetime(
                        airport_code, chunk_start, direction
                    )
            
            # Precyzyjne dopasowanie granic zapytania SQL dla danego wywołania generatora
            query_start = from_local_datetime if i == 0 else chunk_start
            query_end   = min(chunk_end, end_of_query)

            # Pobranie danych z bazy dla aktualnie przetwarzanego okna czasowego
            async with db.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT
                        f.id, f.flight_number, f.airline_code,
                        f.origin_airport_code, f.destination_airport_code,
                        f.scheduled_departure_utc, f.scheduled_departure_local,
                        f.scheduled_arrival_utc, f.scheduled_arrival_local,
                        f.departure_terminal, f.departure_gate,
                        f.search_date, f.created_at,
                        a1.name as airline_name,
                        c1.code as origin_city_code,
                        c2.code as destination_city_code
                    FROM flights f
                    LEFT JOIN airlines a1 ON f.airline_code = a1.code
                    LEFT JOIN airports ap1 ON f.origin_airport_code = ap1.code
                    LEFT JOIN airports ap2 ON f.destination_airport_code = ap2.code
                    LEFT JOIN cities c1 ON ap1.city_code = c1.code
                    LEFT JOIN cities c2 ON ap2.city_code = c2.code
                    WHERE f.origin_airport_code = $1
                      AND f.scheduled_departure_local >= $2
                      AND f.scheduled_departure_local <= $3
                    ORDER BY f.scheduled_departure_local ASC
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
            
            # Przekazanie przetworzonej paczki danych do odbiorcy strumienia
            yield FlightsResponse(
                data=flights,
                count=total_count or 0,
                last_fetched_at=info['last_fetched_at'] if info else None,
                range_end_datetime=query_end.isoformat()
            )

    @staticmethod
    async def get_flights_from_airport(
        airport_code: str,
        from_local_datetime: Optional[datetime] = None,
        search_date: Optional[date] = None,
        limit: int = 200,
        force_refresh: bool = False,
        to_local_datetime: Optional[datetime] = None,
    ) -> FlightsResponse:
        # Pobiera pełną listę lotów w zadanym zakresie czasowym (metoda blokująca).
        # Agreguje wyniki z wielu potencjalnych okien czasowych w jedną odpowiedź.
        direction = settings.default_flight_direction

        if from_local_datetime is None:
            if search_date is not None:
                from_local_datetime = datetime.combine(search_date, time.min)
            else:
                from_local_datetime = datetime.utcnow().replace(second=0, microsecond=0)

        airport_tz = await FlightScheduleService._get_airport_tz(airport_code)
        utc_now = datetime.now(pytz.UTC)
        local_now = utc_now.astimezone(airport_tz)
        local_today = local_now.date()

        from_date = from_local_datetime.date()

        if to_local_datetime is not None:
            end_of_query = to_local_datetime
        else:
            end_of_query = datetime.combine(from_local_datetime.date(), time.max)

        chunks_needed = FlightScheduleService._get_chunks_for_range(
            from_local_datetime, end_of_query, local_today
        )

        # Zapewnienie aktualności danych w cache dla każdego wymaganego okna
        last_fetched = None
        for chunk_start in chunks_needed:
            if force_refresh:
                await FlightScheduleService.fetch_and_cache_schedules(
                    airport_code, chunk_start, direction
                )
                info = await FlightScheduleService.find_cache_for_datetime(
                    airport_code, chunk_start, direction
                )
            else:
                info = await FlightScheduleService.find_cache_for_datetime(
                    airport_code, chunk_start, direction
                )
                if not info:
                    await FlightScheduleService.fetch_and_cache_schedules(
                        airport_code, chunk_start, direction
                    )
                    info = await FlightScheduleService.find_cache_for_datetime(
                        airport_code, chunk_start, direction
                    )
            if info and info['last_fetched_at']:
                if last_fetched is None or info['last_fetched_at'] > last_fetched:
                    last_fetched = info['last_fetched_at']

        async with db.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT
                    f.id, f.flight_number, f.airline_code,
                    f.origin_airport_code, f.destination_airport_code,
                    f.scheduled_departure_utc, f.scheduled_departure_local,
                    f.scheduled_arrival_utc, f.scheduled_arrival_local,
                    f.departure_terminal, f.departure_gate,
                    f.search_date, f.created_at,
                    a1.name as airline_name,
                    c1.code as origin_city_code,
                    c2.code as destination_city_code
                FROM flights f
                LEFT JOIN airlines a1 ON f.airline_code = a1.code
                LEFT JOIN airports ap1 ON f.origin_airport_code = ap1.code
                LEFT JOIN airports ap2 ON f.destination_airport_code = ap2.code
                LEFT JOIN cities c1 ON ap1.city_code = c1.code
                LEFT JOIN cities c2 ON ap2.city_code = c2.code
                WHERE f.origin_airport_code = $1
                  AND f.scheduled_departure_local >= $2
                  AND f.scheduled_departure_local <= $3
                ORDER BY f.scheduled_departure_local ASC
                LIMIT $4
            """, airport_code, from_local_datetime, end_of_query, limit)

            total_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM flights
                WHERE origin_airport_code = $1
                  AND scheduled_departure_local >= $2
                  AND scheduled_departure_local <= $3
            """, airport_code, from_local_datetime, end_of_query)

        flights = [Flight(**dict(row)) for row in rows]

        return FlightsResponse(
            data=flights,
            count=total_count or 0,
            last_fetched_at=last_fetched,
            range_end_datetime=end_of_query.isoformat()
        )


# Globalna instancja serwisu harmonogramów lotów
flight_schedule_service = FlightScheduleService()

