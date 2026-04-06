
-- Usuń lotniska z nieistniejącymi miastami
DELETE FROM airports
WHERE city_code IS NOT NULL AND city_code NOT IN (SELECT code FROM cities);

-- Klucze obce dla lotnisk
ALTER TABLE airports
ADD CONSTRAINT fk_airports_city
FOREIGN KEY (city_code) REFERENCES cities(code)
ON DELETE CASCADE;

-- Klucze obce dla tabel API
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

-- Indeksy dla szybkiego wyszukiwania nazw i powiązań geograficznych
CREATE INDEX idx_cities_name ON cities(name);
CREATE INDEX idx_cities_country ON cities(country_code);
CREATE INDEX idx_airlines_name ON airlines(name);
CREATE INDEX idx_airports_name ON airports(name);
CREATE INDEX idx_airports_city ON airports(city_code);
CREATE INDEX idx_airports_country ON airports(country_code);

-- Indeksy dla tabel API harmonogramów lotów
CREATE INDEX idx_schedules_airport_datetime ON airport_schedules_cache(airport_code, direction, fetch_from_local, fetch_to_local);
CREATE INDEX idx_schedules_fetched ON airport_schedules_cache(last_fetched_at);
CREATE INDEX idx_flights_origin_date ON flights(origin_airport_code, search_date);
CREATE INDEX idx_flights_destination_date ON flights(destination_airport_code, search_date);
CREATE INDEX idx_flights_origin_departure_local ON flights(origin_airport_code, scheduled_departure_local);
CREATE INDEX idx_flights_departure_utc ON flights(scheduled_departure_utc);
CREATE INDEX idx_flights_flight_number ON flights(flight_number);
CREATE INDEX idx_flights_airline ON flights(airline_code);
CREATE INDEX idx_flights_origin_dest ON flights(origin_airport_code, destination_airport_code);

-- Indeksy dla tabel API ofert cenowych
CREATE INDEX idx_prices_origin_dest_date ON flight_prices_cache(origin_city_code, destination_city_code, departure_date);
CREATE INDEX idx_prices_fetched ON flight_prices_cache(last_fetched_at);
CREATE INDEX idx_offers_origin_airport_date ON flight_offers(origin_airport_code, search_date);
CREATE INDEX idx_offers_destination_airport_date ON flight_offers(destination_airport_code, search_date);
CREATE INDEX idx_offers_departure_at ON flight_offers(departure_at);
CREATE INDEX idx_offers_city_origin_date ON flight_offers(origin_city_code, destination_city_code, search_date);
CREATE INDEX idx_offers_price ON flight_offers(price);

-- Przeniesione indeksy tabeli planów podróży tworzone po zakończeniu masowego ładowania danych
CREATE INDEX IF NOT EXISTS idx_user_trips_user_id ON user_trips (user_id);
CREATE INDEX IF NOT EXISTS idx_user_trips_updated  ON user_trips (updated_at DESC);

-- Generowanie raportu statystycznego informującego o liczbie zaimportowanych rekordów w głównych tabelach systemu
DO $$
DECLARE
    cities_count INTEGER;
    airports_count INTEGER;
    airlines_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO cities_count FROM cities;
    SELECT COUNT(*) INTO airports_count FROM airports;
    SELECT COUNT(*) INTO airlines_count FROM airlines;

    RAISE NOTICE 'Podsumowanie procesu inicjalizacji bazy danych';
    RAISE NOTICE 'Załadowano miast %', cities_count;
    RAISE NOTICE 'Załadowano lotnisk %', airports_count;
    RAISE NOTICE 'Załadowano linii lotniczych %', airlines_count;
END $$;
