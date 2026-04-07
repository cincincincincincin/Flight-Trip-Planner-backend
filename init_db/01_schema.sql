-- Usunięcie starych tabel
DROP TABLE IF EXISTS flight_offers, flight_prices_cache, flights, airport_schedules_cache CASCADE;
DROP TABLE IF EXISTS airlines, airports, cities CASCADE;

-- Miasta (Tylko kody, nazwy są we frontendzie)
CREATE TABLE cities (
    code VARCHAR(10) PRIMARY KEY
);

-- Lotniska (Kody, city_code i strefy czasowe dla logiki backendu)
CREATE TABLE airports (
    code VARCHAR(4) PRIMARY KEY,
    city_code VARCHAR(10),
    time_zone VARCHAR(50)
);

-- Cache dla schedules z AeroDataBox API
CREATE TABLE airport_schedules_cache (
    id SERIAL PRIMARY KEY,
    airport_code VARCHAR(4) NOT NULL,
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('Departure', 'Arrival', 'Both')),
    last_fetched_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    data JSONB NOT NULL,
    fetch_from_local TIMESTAMP NOT NULL,
    fetch_to_local TIMESTAMP NOT NULL,
    UNIQUE(airport_code, direction, fetch_from_local)
);

-- Pojedyncze loty (Ultra-Lean: brak złączeń, nazwa linii bezpośrednio w wierszu)
CREATE TABLE flights (
    id SERIAL PRIMARY KEY,
    flight_number VARCHAR(20) NOT NULL,
    airline_code VARCHAR(3),
    airline_name VARCHAR(200), -- Przechowywana bezpośrednio (Fresh from API)
    origin_airport_code VARCHAR(4) NOT NULL,
    destination_airport_code VARCHAR(4) NOT NULL,
    scheduled_departure_utc TIMESTAMP WITH TIME ZONE NOT NULL,
    scheduled_departure_local TIMESTAMP,
    scheduled_arrival_utc TIMESTAMP WITH TIME ZONE,
    scheduled_arrival_local TIMESTAMP,
    departure_terminal VARCHAR(10),
    departure_gate VARCHAR(10),
    api_raw JSONB, -- Pełna odpowiedź z API (aircraft, status, etc.)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(flight_number, scheduled_departure_utc, origin_airport_code, destination_airport_code)
);

-- Cache dla cen biletów z Aviasales API
CREATE TABLE flight_prices_cache (
    id SERIAL PRIMARY KEY,
    origin_city_code VARCHAR(10) NOT NULL,
    destination_city_code VARCHAR(10) NOT NULL,
    departure_date DATE NOT NULL,
    currency VARCHAR(3) NOT NULL,
    last_fetched_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    data JSONB NOT NULL,
    UNIQUE(origin_city_code, destination_city_code, departure_date, currency)
);

-- Pojedyncze oferty biletów (Ultra-Lean: nazwa linii bezpośrednio)
CREATE TABLE flight_offers (
    id SERIAL PRIMARY KEY,
    origin_city_code VARCHAR(10) NOT NULL,
    destination_city_code VARCHAR(10) NOT NULL,
    origin_airport_code VARCHAR(4) NOT NULL,
    destination_airport_code VARCHAR(4) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    airline_code VARCHAR(3),
    flight_number VARCHAR(20),
    departure_at TIMESTAMP NOT NULL,
    link TEXT,
    api_raw JSONB, -- Pełna odpowiedź z API (gate, transfers, duration, etc.)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(origin_airport_code, destination_airport_code, departure_at, flight_number, price)
);

-- Plany podróży użytkownika
CREATE TABLE IF NOT EXISTS user_trips (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT,
    trip_state  JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Preferencje użytkownika język, styl mapy, kolory, rozmiary
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id    TEXT PRIMARY KEY,
    data       JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
