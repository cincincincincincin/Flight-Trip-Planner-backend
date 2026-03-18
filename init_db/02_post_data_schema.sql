-- 3. CZYSZCZENIE DANYCH Z PROBLEMAMI
-- ============================================

-- 3.1 Usuń lotniska z flightable = false ORAZ lotniska z typem innym niż 'airport' (ignorując NULL)
DELETE FROM airports WHERE flightable = false OR (iata_type IS NOT NULL AND iata_type != 'airport');

-- 3.2 Usuń miasta z has_flightable_airport = false
DELETE FROM cities WHERE has_flightable_airport = false;

-- 3.3 Usuń miasta z nieistniejącymi krajami
DELETE FROM cities
WHERE country_code IS NOT NULL
  AND country_code NOT IN (SELECT code FROM countries);

-- 3.4 Usuń lotniska z nieistniejącymi miastami lub krajami
DELETE FROM airports
WHERE (city_code IS NOT NULL AND city_code NOT IN (SELECT code FROM cities))
   OR (country_code IS NOT NULL AND country_code NOT IN (SELECT code FROM countries));

-- 3.5 Usuń trasy z nieistniejącymi referencjami
DELETE FROM routes
WHERE (airline_iata IS NOT NULL AND airline_iata NOT IN (SELECT code FROM airlines))
   OR (departure_airport_iata IS NOT NULL AND departure_airport_iata NOT IN (SELECT code FROM airports))
   OR (arrival_airport_iata IS NOT NULL AND arrival_airport_iata NOT IN (SELECT code FROM airports));

-- ============================================
-- 4. DODANIE KLUCZY OBCYCH
-- ============================================

-- 4.1 Klucze obce dla miast
ALTER TABLE cities
ADD CONSTRAINT fk_cities_country
FOREIGN KEY (country_code) REFERENCES countries(code)
ON DELETE CASCADE;

-- 4.2 Klucze obce dla lotnisk
ALTER TABLE airports
ADD CONSTRAINT fk_airports_city
FOREIGN KEY (city_code) REFERENCES cities(code)
ON DELETE CASCADE,
ADD CONSTRAINT fk_airports_country
FOREIGN KEY (country_code) REFERENCES countries(code)
ON DELETE CASCADE;

-- 4.3 Klucze obce dla tras
ALTER TABLE routes
ADD CONSTRAINT fk_routes_airline
FOREIGN KEY (airline_iata) REFERENCES airlines(code)
ON DELETE CASCADE,
ADD CONSTRAINT fk_routes_departure_airport
FOREIGN KEY (departure_airport_iata) REFERENCES airports(code)
ON DELETE CASCADE,
ADD CONSTRAINT fk_routes_arrival_airport
FOREIGN KEY (arrival_airport_iata) REFERENCES airports(code)
ON DELETE CASCADE;

-- 4.4 Klucze obce dla tabel API
ALTER TABLE airport_schedules_cache
ADD CONSTRAINT fk_schedules_airport
FOREIGN KEY (airport_code) REFERENCES airports(code)
ON DELETE CASCADE;

ALTER TABLE flights
ADD CONSTRAINT fk_flights_airline
FOREIGN KEY (airline_code) REFERENCES airlines(code)
ON DELETE SET NULL,
ADD CONSTRAINT fk_flights_origin_airport
FOREIGN KEY (origin_airport_code) REFERENCES airports(code)
ON DELETE CASCADE,
ADD CONSTRAINT fk_flights_destination_airport
FOREIGN KEY (destination_airport_code) REFERENCES airports(code)
ON DELETE CASCADE;

ALTER TABLE flight_prices_cache
ADD CONSTRAINT fk_prices_origin_city
FOREIGN KEY (origin_city_code) REFERENCES cities(code)
ON DELETE CASCADE,
ADD CONSTRAINT fk_prices_destination_city
FOREIGN KEY (destination_city_code) REFERENCES cities(code)
ON DELETE CASCADE;

ALTER TABLE flight_offers
ADD CONSTRAINT fk_offers_airline
FOREIGN KEY (airline_code) REFERENCES airlines(code)
ON DELETE SET NULL,
ADD CONSTRAINT fk_offers_origin_city
FOREIGN KEY (origin_city_code) REFERENCES cities(code)
ON DELETE CASCADE,
ADD CONSTRAINT fk_offers_destination_city
FOREIGN KEY (destination_city_code) REFERENCES cities(code)
ON DELETE CASCADE,
ADD CONSTRAINT fk_offers_origin_airport
FOREIGN KEY (origin_airport_code) REFERENCES airports(code)
ON DELETE CASCADE,
ADD CONSTRAINT fk_offers_destination_airport
FOREIGN KEY (destination_airport_code) REFERENCES airports(code)
ON DELETE CASCADE;

-- ============================================
-- 5. OPTYMALIZACJA I INDEKSY
-- ============================================

-- Indeksy dla szybkiego wyszukiwania
CREATE INDEX idx_countries_name ON countries(name);
CREATE INDEX idx_countries_currency ON countries(currency);

CREATE INDEX idx_cities_name ON cities(name);
CREATE INDEX idx_cities_country ON cities(country_code);
CREATE INDEX idx_cities_has_airport ON cities(has_flightable_airport);

CREATE INDEX idx_airlines_name ON airlines(name);
CREATE INDEX idx_airlines_lowcost ON airlines(is_lowcost);

CREATE INDEX idx_airports_name ON airports(name);
CREATE INDEX idx_airports_city ON airports(city_code);
CREATE INDEX idx_airports_country ON airports(country_code);
CREATE INDEX idx_airports_type ON airports(iata_type);
CREATE INDEX idx_airports_flightable ON airports(flightable);

CREATE INDEX idx_planes_name ON planes(name);

CREATE INDEX idx_routes_airline ON routes(airline_iata);
CREATE INDEX idx_routes_departure ON routes(departure_airport_iata);
CREATE INDEX idx_routes_arrival ON routes(arrival_airport_iata);
CREATE INDEX idx_routes_codeshare ON routes(codeshare);
CREATE INDEX idx_routes_transfers ON routes(transfers);

-- Indeksy dla zapytań JSON
CREATE INDEX idx_routes_planes_gin ON routes USING gin(planes);
CREATE INDEX idx_countries_translations ON countries USING gin(name_translations);
CREATE INDEX idx_cities_translations ON cities USING gin(name_translations);
CREATE INDEX idx_airlines_translations ON airlines USING gin(name_translations);
CREATE INDEX idx_airports_translations ON airports USING gin(name_translations);

-- Indeksy dla wyszukiwania case-insensitive
CREATE INDEX idx_countries_name_lower ON countries(LOWER(name));
CREATE INDEX idx_cities_name_lower ON cities(LOWER(name));
CREATE INDEX idx_airports_name_lower ON airports(LOWER(name));

-- Indeksy dla tabel API
CREATE INDEX idx_schedules_airport_datetime ON airport_schedules_cache(airport_code, direction, fetch_from_local, fetch_to_local);
CREATE INDEX idx_schedules_fetched ON airport_schedules_cache(last_fetched_at);

CREATE INDEX idx_flights_origin_date ON flights(origin_airport_code, search_date);
CREATE INDEX idx_flights_destination_date ON flights(destination_airport_code, search_date);
CREATE INDEX idx_flights_origin_departure_local ON flights(origin_airport_code, scheduled_departure_local);
CREATE INDEX idx_flights_departure_utc ON flights(scheduled_departure_utc);
CREATE INDEX idx_flights_flight_number ON flights(flight_number);
CREATE INDEX idx_flights_airline ON flights(airline_code);
CREATE INDEX idx_flights_origin_dest ON flights(origin_airport_code, destination_airport_code);

CREATE INDEX idx_prices_origin_dest_date ON flight_prices_cache(origin_city_code, destination_city_code, departure_date);
CREATE INDEX idx_prices_fetched ON flight_prices_cache(last_fetched_at);

CREATE INDEX idx_offers_origin_airport_date ON flight_offers(origin_airport_code, search_date);
CREATE INDEX idx_offers_destination_airport_date ON flight_offers(destination_airport_code, search_date);
CREATE INDEX idx_offers_departure_at ON flight_offers(departure_at);
CREATE INDEX idx_offers_city_origin_date ON flight_offers(origin_city_code, destination_city_code, search_date);
CREATE INDEX idx_offers_price ON flight_offers(price);
CREATE INDEX idx_offers_transfers ON flight_offers(transfers);

-- ============================================
-- 6. WIDOKI DLA WYGODY
-- ============================================

-- Widok z pełnymi danymi tras
CREATE OR REPLACE VIEW routes_details AS
SELECT
    r.id,
    a.name as airline_name,
    r.airline_iata,
    ap1.name as departure_airport,
    ap1.code as departure_iata,
    c1.name as departure_city,
    co1.name as departure_country,
    ap2.name as arrival_airport,
    ap2.code as arrival_iata,
    c2.name as arrival_city,
    co2.name as arrival_country,
    r.codeshare,
    r.transfers,
    r.planes,
    ap1.coordinates as departure_coords,
    ap2.coordinates as arrival_coords
FROM routes r
LEFT JOIN airlines a ON r.airline_iata = a.code
LEFT JOIN airports ap1 ON r.departure_airport_iata = ap1.code
LEFT JOIN cities c1 ON ap1.city_code = c1.code
LEFT JOIN countries co1 ON ap1.country_code = co1.code
LEFT JOIN airports ap2 ON r.arrival_airport_iata = ap2.code
LEFT JOIN cities c2 ON ap2.city_code = c2.code
LEFT JOIN countries co2 ON ap2.country_code = co2.code
WHERE r.departure_airport_iata IS NOT NULL
  AND r.arrival_airport_iata IS NOT NULL;

-- Widok lotnisk z miastem i krajem
CREATE OR REPLACE VIEW airports_details AS
SELECT
    a.code,
    a.name,
    a.city_code,
    a.country_code,
    a.time_zone,
    a.coordinates,
    a.flightable,
    a.iata_type,
    c.name as city_name,
    co.name as country_name
FROM airports a
LEFT JOIN cities c ON a.city_code = c.code
LEFT JOIN countries co ON a.country_code = co.code;

-- Widok miast z krajem i informacją o lotniskach
CREATE OR REPLACE VIEW cities_details AS
SELECT
    c.code,
    c.name,
    c.country_code,
    c.time_zone,
    c.coordinates,
    c.has_flightable_airport,
    co.name as country_name,
    co.currency,
    COUNT(a.code) as airport_count,
    SUM(CASE WHEN a.flightable THEN 1 ELSE 0 END) as flightable_airport_count
FROM cities c
LEFT JOIN countries co ON c.country_code = co.code
LEFT JOIN airports a ON c.code = a.city_code
GROUP BY c.code, c.name, c.country_code, c.time_zone, c.coordinates,
         c.has_flightable_airport, co.name, co.currency;

-- Widok lotów z pełnymi danymi lotnisk
CREATE OR REPLACE VIEW flights_details AS
SELECT
    f.id,
    f.flight_number,
    a.name as airline_name,
    f.airline_code,
    ap1.name as origin_airport_name,
    ap1.code as origin_airport_code,
    c1.name as origin_city_name,
    c1.code as origin_city_code,
    ap2.name as destination_airport_name,
    ap2.code as destination_airport_code,
    c2.name as destination_city_name,
    c2.code as destination_city_code,
    f.scheduled_departure_utc,
    f.scheduled_departure_local,
    f.scheduled_arrival_utc,
    f.scheduled_arrival_local,
    f.departure_terminal,
    f.departure_gate,
    f.arrival_terminal,
    f.arrival_gate,
    f.search_date,
    f.created_at
FROM flights f
LEFT JOIN airlines a ON f.airline_code = a.code
LEFT JOIN airports ap1 ON f.origin_airport_code = ap1.code
LEFT JOIN cities c1 ON ap1.city_code = c1.code
LEFT JOIN airports ap2 ON f.destination_airport_code = ap2.code
LEFT JOIN cities c2 ON ap2.city_code = c2.code;

-- Widok ofert biletów z pełnymi danymi
CREATE OR REPLACE VIEW flight_offers_details AS
SELECT
    fo.id,
    fo.flight_number,
    a.name as airline_name,
    fo.airline_code,
    oc.name as origin_city_name,
    oc.code as origin_city_code,
    dc.name as destination_city_name,
    dc.code as destination_city_code,
    oa.name as origin_airport_name,
    oa.code as origin_airport_code,
    da.name as destination_airport_name,
    da.code as destination_airport_code,
    fo.price,
    fo.currency,
    fo.departure_at,
    fo.return_at,
    fo.transfers,
    fo.duration_to,
    fo.link,
    fo.search_date,
    fo.created_at
FROM flight_offers fo
LEFT JOIN airlines a ON fo.airline_code = a.code
LEFT JOIN cities oc ON fo.origin_city_code = oc.code
LEFT JOIN cities dc ON fo.destination_city_code = dc.code
LEFT JOIN airports oa ON fo.origin_airport_code = oa.code
LEFT JOIN airports da ON fo.destination_airport_code = da.code;

-- ============================================
-- 7. STATYSTYKI (dla debugowania)
-- ============================================

DO $$
DECLARE
    countries_count INTEGER;
    cities_count INTEGER;
    airports_count INTEGER;
    airlines_count INTEGER;
    routes_count INTEGER;
    planes_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO countries_count FROM countries;
    SELECT COUNT(*) INTO cities_count FROM cities;
    SELECT COUNT(*) INTO airports_count FROM airports;
    SELECT COUNT(*) INTO airlines_count FROM airlines;
    SELECT COUNT(*) INTO routes_count FROM routes;
    SELECT COUNT(*) INTO planes_count FROM planes;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'STATYSTYKI PO CZYSZCZENIU:';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Kraje: %', countries_count;
    RAISE NOTICE 'Miasta: %', cities_count;
    RAISE NOTICE 'Lotniska: %', airports_count;
    RAISE NOTICE 'Linie lotnicze: %', airlines_count;
    RAISE NOTICE 'Trasy: %', routes_count;
    RAISE NOTICE 'Samoloty: %', planes_count;
    RAISE NOTICE '============================================';
    RAISE NOTICE 'NOWE TABELE API:';
    RAISE NOTICE 'airport_schedules_cache: utworzona';
    RAISE NOTICE 'flights: utworzona';
    RAISE NOTICE 'flight_prices_cache: utworzona';
    RAISE NOTICE 'flight_offers: utworzona';
    RAISE NOTICE '============================================';
END $$;

-- ============================================
-- 8. FUNKCJE POMOCNICZE
-- ============================================

-- Funkcja do sprawdzania, czy lotnisko ma trasy
CREATE OR REPLACE FUNCTION airport_has_routes(airport_code VARCHAR)
RETURNS BOOLEAN AS $$
DECLARE
    has_routes BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM routes
        WHERE departure_airport_iata = airport_code
           OR arrival_airport_iata = airport_code
    ) INTO has_routes;

    RETURN has_routes;
END;
$$ LANGUAGE plpgsql;

-- Funkcja do liczenia tras dla lotniska
CREATE OR REPLACE FUNCTION count_airport_routes(airport_code VARCHAR)
RETURNS INTEGER AS $$
DECLARE
    route_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO route_count
    FROM routes
    WHERE departure_airport_iata = airport_code
       OR arrival_airport_iata = airport_code;

    RETURN route_count;
END;
$$ LANGUAGE plpgsql;

-- Funkcja do znajdowania tras między lotniskami
CREATE OR REPLACE FUNCTION find_routes_between_airports(
    departure_code VARCHAR,
    arrival_code VARCHAR,
    max_transfers INTEGER DEFAULT 0
)
RETURNS TABLE(
    route_id INTEGER,
    airline_iata VARCHAR,
    departure_airport_iata VARCHAR,
    arrival_airport_iata VARCHAR,
    transfers INTEGER,
    codeshare BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id,
        r.airline_iata,
        r.departure_airport_iata,
        r.arrival_airport_iata,
        r.transfers,
        r.codeshare
    FROM routes r
    WHERE r.departure_airport_iata = departure_code
      AND r.arrival_airport_iata = arrival_code
      AND r.transfers <= max_transfers
    ORDER BY r.transfers, r.codeshare;
END;
$$ LANGUAGE plpgsql;

-- Funkcja do sprawdzania czy są zcache'owane schedules dla lotniska i datetimem
CREATE OR REPLACE FUNCTION has_cached_schedules(
    airport_code_param VARCHAR,
    from_datetime_param TIMESTAMP,
    direction_param VARCHAR DEFAULT 'Departure'
)
RETURNS BOOLEAN AS $$
DECLARE
    has_cache BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM airport_schedules_cache
        WHERE airport_code = airport_code_param
          AND direction = direction_param
          AND fetch_from_local <= from_datetime_param
          AND fetch_to_local > from_datetime_param
          AND last_fetched_at > (NOW() - INTERVAL '1 hour')
    ) INTO has_cache;

    RETURN has_cache;
END;
$$ LANGUAGE plpgsql;

-- Funkcja do sprawdzania czy są zcache'owane ceny dla miast i daty
CREATE OR REPLACE FUNCTION has_cached_prices(
    origin_city_param VARCHAR,
    destination_city_param VARCHAR,
    departure_date_param DATE
)
RETURNS BOOLEAN AS $$
DECLARE
    has_cache BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM flight_prices_cache
        WHERE origin_city_code = origin_city_param
          AND destination_city_code = destination_city_param
          AND departure_date = departure_date_param
    ) INTO has_cache;

    RETURN has_cache;
END;
$$ LANGUAGE plpgsql;

-- Funkcja do pobierania lotów z danego lotniska dla danej daty (chronologicznie)
CREATE OR REPLACE FUNCTION get_flights_from_airport(
    airport_code_param VARCHAR,
    search_date_param DATE,
    limit_param INTEGER DEFAULT 50,
    offset_param INTEGER DEFAULT 0
)
RETURNS TABLE(
    id INTEGER,
    flight_number VARCHAR,
    airline_code VARCHAR,
    origin_airport_code VARCHAR,
    destination_airport_code VARCHAR,
    scheduled_departure_utc TIMESTAMP WITH TIME ZONE,
    scheduled_departure_local TIMESTAMP WITH TIME ZONE,
    scheduled_arrival_utc TIMESTAMP WITH TIME ZONE,
    scheduled_arrival_local TIMESTAMP WITH TIME ZONE,
    departure_terminal VARCHAR,
    departure_gate VARCHAR,
    arrival_terminal VARCHAR,
    arrival_gate VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        f.id,
        f.flight_number,
        f.airline_code,
        f.origin_airport_code,
        f.destination_airport_code,
        f.scheduled_departure_utc,
        f.scheduled_departure_local,
        f.scheduled_arrival_utc,
        f.scheduled_arrival_local,
        f.departure_terminal,
        f.departure_gate,
        f.arrival_terminal,
        f.arrival_gate
    FROM flights f
    WHERE f.origin_airport_code = airport_code_param
      AND f.search_date = search_date_param
    ORDER BY f.scheduled_departure_utc ASC
    LIMIT limit_param
    OFFSET offset_param;
END;
$$ LANGUAGE plpgsql;

-- Funkcja do pobierania ofert biletów dla lotu (dopasowanie po lotniskach i czasie)
CREATE OR REPLACE FUNCTION get_offers_for_flight(
    origin_airport_param VARCHAR,
    destination_airport_param VARCHAR,
    departure_date_param DATE
)
RETURNS TABLE(
    id INTEGER,
    price DECIMAL,
    currency VARCHAR,
    airline_code VARCHAR,
    flight_number VARCHAR,
    departure_at TIMESTAMP WITH TIME ZONE,
    duration_to INTEGER,
    link TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        fo.id,
        fo.price,
        fo.currency,
        fo.airline_code,
        fo.flight_number,
        fo.departure_at,
        fo.duration_to,
        fo.link
    FROM flight_offers fo
    WHERE fo.origin_airport_code = origin_airport_param
      AND fo.destination_airport_code = destination_airport_param
      AND DATE(fo.departure_at) = departure_date_param
      AND fo.transfers = 0
    ORDER BY fo.price ASC;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- TABELE DLA PLANOWANIA PODRÓŻY
-- ============================================

-- Podróże użytkownika
CREATE TABLE IF NOT EXISTS trips (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200),
    start_airport_code VARCHAR(4) NOT NULL,
    start_date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    FOREIGN KEY (start_airport_code) REFERENCES airports(code) ON DELETE CASCADE
);

-- Loty w podróży
CREATE TABLE IF NOT EXISTS trip_flights (
    id SERIAL PRIMARY KEY,
    trip_id INTEGER NOT NULL,
    flight_id INTEGER NOT NULL,
    flight_order INTEGER NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
    FOREIGN KEY (flight_id) REFERENCES flights(id) ON DELETE CASCADE,
    UNIQUE(trip_id, flight_order)
);

-- Zapisane oferty biletów dla lotów w podróży
CREATE TABLE IF NOT EXISTS trip_flight_prices (
    id SERIAL PRIMARY KEY,
    trip_flight_id INTEGER NOT NULL,
    offer_id INTEGER,
    price DECIMAL(10, 2),
    currency VARCHAR(3),
    link TEXT,
    found_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    FOREIGN KEY (trip_flight_id) REFERENCES trip_flights(id) ON DELETE CASCADE,
    FOREIGN KEY (offer_id) REFERENCES flight_offers(id) ON DELETE SET NULL
);

-- Indeksy
CREATE INDEX idx_trips_start_airport ON trips(start_airport_code);
CREATE INDEX idx_trips_start_date ON trips(start_date);
CREATE INDEX idx_trip_flights_trip ON trip_flights(trip_id);
CREATE INDEX idx_trip_flights_order ON trip_flights(trip_id, flight_order);
CREATE INDEX idx_trip_prices_trip_flight ON trip_flight_prices(trip_flight_id);

-- Funkcja do pobierania podróży z lotami
CREATE OR REPLACE FUNCTION get_trip_details(trip_id_param INTEGER)
RETURNS TABLE(
    trip_id INTEGER,
    trip_name VARCHAR,
    start_airport_code VARCHAR,
    start_date DATE,
    flight_order INTEGER,
    flight_number VARCHAR,
    origin_airport_code VARCHAR,
    destination_airport_code VARCHAR,
    scheduled_departure_utc TIMESTAMP WITH TIME ZONE,
    price DECIMAL,
    currency VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.id,
        t.name,
        t.start_airport_code,
        t.start_date,
        tf.flight_order,
        f.flight_number,
        f.origin_airport_code,
        f.destination_airport_code,
        f.scheduled_departure_utc,
        tfp.price,
        tfp.currency
    FROM trips t
    JOIN trip_flights tf ON t.id = tf.trip_id
    JOIN flights f ON tf.flight_id = f.id
    LEFT JOIN trip_flight_prices tfp ON tf.id = tfp.trip_flight_id
    WHERE t.id = trip_id_param
    ORDER BY tf.flight_order;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 9. GRANTY (jeśli używasz różnych użytkowników)
-- ============================================

-- Przykładowe granty dla użytkownika aplikacji
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_user;
-- GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO app_user;

-- ============================================
-- KONIEC INICJALIZACJI
-- ============================================
