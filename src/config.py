from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = Field(..., description="PostgreSQL connection URL")

    # Redis
    redis_url: str = Field(..., description="Redis connection URL")

    # API keys
    aerodatabox_api_key: str = Field('', description="AeroDataBox / RapidAPI key")
    aviasales_api_token: str = Field('', description="Aviasales API token")
    rapidapi_host: str = Field('aerodatabox.p.rapidapi.com', description="RapidAPI host")

    # App
    app_name: str = "Flight Map API"
    debug: bool = False
    log_level: str = "INFO"

    # CORS
    cors_origins: List[str] = ["*"]

    # Auth - Supabase
    supabase_url: str = Field('', description="Supabase project URL for JWKS verification")
    supabase_jwt_secret: str = Field('', description="Supabase JWT secret for HS256 token verification")

    # Database Settings
    database_pool_min_size: int = Field(5, description="Min database pool size")
    database_pool_max_size: int = Field(20, description="Max database pool size")
    database_command_timeout: int = Field(60, description="Database command timeout")

    # Redis Settings
    redis_connect_timeout: int = Field(2, description="Redis connect timeout")
    redis_socket_timeout: int = Field(2, description="Redis socket timeout")

    # Auth
    supabase_jwks_ttl: int = Field(3600, description="Supabase JWKS TTL seconds")
    supabase_jwks_fetch_timeout: float = Field(5.0, description="Supabase JWKS fetch timeout")

    # Flight Schedule Service
    flight_cache_expiry_hours: int = Field(1, description="Flight cache expiry hours")
    aerodatabox_api_call_interval: float = Field(1.5, description="AeroDataBox API call interval")
    aerodatabox_window_hours: int = Field(12, description="AeroDataBox window hours")
    debug_flight_service: bool = Field(True, description="Debug flight service")

    # Flight Price Service
    price_cache_expiry_hours: int = Field(6, description="Price cache expiry hours")
    aviasales_default_limit: int = Field(1000, description="Aviasales default limit")
    debug_price_service: bool = Field(True, description="Debug price service")
    search_max_cities_per_country: int = Field(50, description="Max cities per country phase 2")
    search_max_cities_per_country_phase3: int = Field(20, description="Max cities per country phase 3")
    search_max_airports_per_city: int = Field(10, description="Max airports per city")
    
    # API Client
    aerodatabox_base_url: str = Field("https://aerodatabox.p.rapidapi.com", description="AeroDataBox Base URL")
    aviasales_base_url: str = Field("https://api.travelpayouts.com/aviasales/v3/prices_for_dates", description="Aviasales Base URL")
    aerodatabox_timeout: float = Field(30.0, description="AeroDataBox Timeout")
    aviasales_timeout: float = Field(30.0, description="Aviasales Timeout")
    debug_api_calls: bool = Field(True, description="Debug API Calls")

    # Search Service
    country_center_outlier_degrees: float = Field(5.0, description="Country center outlier degrees")
    country_zoom_levels: dict[str, float] = Field(
        default_factory=lambda: {"0": 5.0, "5": 5.0, "15": 4.5, "40": 3.5, "100": 2.6, "default": 1.8},
        description="Zoom levels based on number of airports"
    )
    search_cities_page_size: int = Field(50, description="Search cities page size")
    search_airports_page_size: int = Field(200, description="Search airports page size")
    debug_log_file: str = Field("debug.log", description="Path to debug log file")

    # Cache TTLs
    cache_ttl_geojson: int = Field(86400, description="Cache TTL GeoJSON")
    cache_ttl_entity: int = Field(86400, description="Cache TTL Entity")
    cache_ttl_search: int = Field(3600, description="Cache TTL Search")
    cache_ttl_expand: int = Field(3600, description="Cache TTL Expand")

    # Default flight settings
    default_currency: str = Field("PLN", description="Default currency")
    default_flight_direction: str = Field("Departure", description="Default flight direction")

    # Rate Limiting
    rate_limit_airports: str = Field("200/minute", description="Rate limit for airports, cities, routes")
    rate_limit_search: str = Field("60/minute", description="Rate limit for search")
    rate_limit_flights: str = Field("30/minute", description="Rate limit for flights, trips")

    @field_validator('database_url')
    @classmethod
    def database_url_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('DATABASE_URL must not be empty')
        return v

    @field_validator('aerodatabox_api_key')
    @classmethod
    def aerodatabox_api_key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('AERODATABOX_API_KEY must not be empty')
        return v

    @field_validator('aviasales_api_token')
    @classmethod
    def aviasales_api_token_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('AVIASALES_API_TOKEN must not be empty')
        return v

    @field_validator('log_level')
    @classmethod
    def log_level_valid(cls, v: str) -> str:
        valid = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f'log_level must be one of {valid}')
        return upper


settings = Settings()  # type: ignore[call-arg]
