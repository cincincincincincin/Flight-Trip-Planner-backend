-- ============================================
-- INICJALIZACJA BAZY DANYCH - WERSJA OPTYMALIZOWANA
-- ZOSTAWIAMY TYLKO LOTNISKA Z TRASAMI
-- ============================================

-- 1. Usunięcie starych tabel
DROP TABLE IF EXISTS flight_offers, flight_prices_cache, flights, airport_schedules_cache CASCADE;
DROP TABLE IF EXISTS airlines, airports, cities, countries CASCADE;
-- DROP TABLE IF EXISTS airlines, airports, cities, countries, planes CASCADE;

-- 1.1 Kraje (z countries.json)
CREATE TABLE countries (
    code VARCHAR(2) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    name_translations JSONB,
    currency VARCHAR(3),
    wikipedia_link TEXT
    -- cases JSONB
);

-- 1.2 Miasta (z cities.json)
CREATE TABLE cities (
    code VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    name_translations JSONB,
    country_code VARCHAR(2),
    time_zone VARCHAR(50),
    coordinates JSONB
    -- cases JSONB
);

-- 1.3 Linie lotnicze (z airlines.json)
CREATE TABLE airlines (
    code VARCHAR(3) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    name_translations JSONB,
    is_lowcost BOOLEAN DEFAULT FALSE
);

-- 1.4 Lotniska (z airports.json)
CREATE TABLE airports (
    code VARCHAR(4) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    name_translations JSONB,
    city_code VARCHAR(10),
    country_code VARCHAR(2),
    time_zone VARCHAR(50),
    coordinates JSONB,
    urls JSONB
);

-- 1.5 Samoloty (z planes.json)
-- CREATE TABLE planes (
--     code VARCHAR(10) PRIMARY KEY,
--     name VARCHAR(100) NOT NULL
-- );

      

-- ============================================
-- 1.7 TABELE DLA ZEWNĘTRZNYCH API
-- ============================================

-- Cache dla schedules z AeroDataBox API (airport departures/arrivals)
-- Każdy rekord reprezentuje jedno 12h okno czasowe
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

-- Pojedyncze loty z AeroDataBox API
CREATE TABLE flights (
    id SERIAL PRIMARY KEY,
    flight_number VARCHAR(20) NOT NULL,
    airline_code VARCHAR(3),
    origin_airport_code VARCHAR(4) NOT NULL,
    destination_airport_code VARCHAR(4) NOT NULL,
    scheduled_departure_utc TIMESTAMP WITH TIME ZONE NOT NULL,
    scheduled_departure_local TIMESTAMP,
    scheduled_arrival_utc TIMESTAMP WITH TIME ZONE,
    scheduled_arrival_local TIMESTAMP,
    revised_departure_utc TIMESTAMP WITH TIME ZONE,
    predicted_departure_utc TIMESTAMP WITH TIME ZONE,
    runway_departure_utc TIMESTAMP WITH TIME ZONE,
    revised_arrival_utc TIMESTAMP WITH TIME ZONE,
    predicted_arrival_utc TIMESTAMP WITH TIME ZONE,
    runway_arrival_utc TIMESTAMP WITH TIME ZONE,
    departure_terminal VARCHAR(10),
    departure_gate VARCHAR(10),
    arrival_terminal VARCHAR(10),
    arrival_gate VARCHAR(10),
    search_date DATE NOT NULL,
    raw_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(flight_number, scheduled_departure_utc, origin_airport_code, destination_airport_code)
);

-- Cache dla cen biletów z Aviasales API
CREATE TABLE flight_prices_cache (
    id SERIAL PRIMARY KEY,
    origin_city_code VARCHAR(3) NOT NULL,
    destination_city_code VARCHAR(3) NOT NULL,
    departure_date DATE NOT NULL,
    last_fetched_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    data JSONB NOT NULL,
    UNIQUE(origin_city_code, destination_city_code, departure_date)
);

-- Pojedyncze oferty biletów z Aviasales API
CREATE TABLE flight_offers (
    id SERIAL PRIMARY KEY,
    origin_city_code VARCHAR(3) NOT NULL,
    destination_city_code VARCHAR(3) NOT NULL,
    origin_airport_code VARCHAR(4) NOT NULL,
    destination_airport_code VARCHAR(4) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    airline_code VARCHAR(3),
    flight_number VARCHAR(20),
    departure_at TIMESTAMP WITH TIME ZONE NOT NULL,
    return_at TIMESTAMP WITH TIME ZONE,
    transfers INTEGER DEFAULT 0,
    return_transfers INTEGER DEFAULT 0,
    duration INTEGER,
    duration_to INTEGER,
    duration_back INTEGER,
    link TEXT,
    search_date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(origin_airport_code, destination_airport_code, departure_at, flight_number, price)
);

CREATE TABLE IF NOT EXISTS user_trips (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,              -- Supabase user UUID (JWT "sub" claim)
    name        TEXT,                       -- optional label, e.g. "Summer 2026"
    trip_state  JSONB NOT NULL,             -- serialized TripState
    trip_routes JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_trips_user_id ON user_trips (user_id);
CREATE INDEX IF NOT EXISTS idx_user_trips_updated  ON user_trips (updated_at DESC);

-- Preferencje użytkownika (język, styl mapy, kolory, rozmiary)
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id    TEXT PRIMARY KEY,
    data       JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

