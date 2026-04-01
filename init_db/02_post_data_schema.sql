
-- Usuń miasta z nieistniejącymi krajami
DELETE FROM cities
WHERE country_code IS NOT NULL
  AND country_code NOT IN (SELECT code FROM countries);

-- Usuń lotniska z nieistniejącymi miastami lub krajami
DELETE FROM airports
WHERE (city_code IS NOT NULL AND city_code NOT IN (SELECT code FROM cities))
   OR (country_code IS NOT NULL AND country_code NOT IN (SELECT code FROM countries));

      

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

CREATE INDEX idx_airlines_name ON airlines(name);
CREATE INDEX idx_airlines_lowcost ON airlines(is_lowcost);

CREATE INDEX idx_airports_name ON airports(name);
CREATE INDEX idx_airports_city ON airports(city_code);
CREATE INDEX idx_airports_country ON airports(country_code);


      
CREATE INDEX idx_countries_translations ON countries USING gin(name_translations);
CREATE INDEX idx_cities_translations ON cities USING gin(name_translations);
CREATE INDEX idx_airlines_translations ON airlines USING gin(name_translations);
CREATE INDEX idx_airports_translations ON airports USING gin(name_translations);

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

      

-- Widok lotnisk z miastem i krajem
CREATE OR REPLACE VIEW airports_details AS
SELECT
    a.code,
    a.name,
    a.city_code,
    a.country_code,
    a.time_zone,
    a.coordinates,
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
    co.name as country_name,
    co.currency,
    COUNT(a.code) as airport_count
FROM cities c
LEFT JOIN countries co ON c.country_code = co.code
LEFT JOIN airports a ON c.code = a.city_code
GROUP BY c.code, c.name, c.country_code, c.time_zone, c.coordinates,
         co.name, co.currency;

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
      
    -- planes_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO countries_count FROM countries;
    SELECT COUNT(*) INTO cities_count FROM cities;
    SELECT COUNT(*) INTO airports_count FROM airports;
    SELECT COUNT(*) INTO airlines_count FROM airlines;
      
    -- SELECT COUNT(*) INTO planes_count FROM planes;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'STATYSTYKI PO CZYSZCZENIU:';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Kraje: %', countries_count;
    RAISE NOTICE 'Miasta: %', cities_count;
    RAISE NOTICE 'Lotniska: %', airports_count;
    RAISE NOTICE 'Linie lotnicze: %', airlines_count;
      
    -- RAISE NOTICE 'Samoloty: %', planes_count;
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
-- TTL: 6 godzin — spójne z price_cache_expiry_hours w Python
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
          AND last_fetched_at > (NOW() - INTERVAL '6 hours')
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

