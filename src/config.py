from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Any

class Settings(BaseSettings):
    # Konfiguracja ładowana z pliku .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Parametry połączeń
    database_url: str = Field(...)
    redis_url: str = Field(...)

    # Klucze dostępu Aerodatabox i Travelpayouts
    aerodatabox_api_key: str = Field(...)
    aviasales_api_token: str = Field(...)
    rapidapi_host: str = Field('aerodatabox.p.rapidapi.com')

    # Ogólna konfiguracja serwera
    app_name: str = "Flight Map API"
    debug: bool = False
    log_level: str = "INFO"

    # Lista dopuszczalnych źródeł CORS które mogą łączyć się z API
    cors_origins: Any = Field(...)

    @field_validator('cors_origins', mode='before')
    @classmethod
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str]:
        # Parsowanie CORS_ORIGINS z env
        if isinstance(v, str):
            return [i.strip() for i in v.split(",")]
        return v

    # Integracja z systemem autoryzacji Supabase
    supabase_url: str = Field('')
    supabase_jwt_secret: str = Field('')

    # Pula połączeń bazy danych i limity czasowe
    database_pool_min_size: int = Field(5)
    database_pool_max_size: int = Field(20)
    database_command_timeout: int = Field(60)

    # Parametry połączenia z Redis
    redis_connect_timeout: int = Field(2)
    redis_socket_timeout: int = Field(2)

    # Weryfikacja sesji JWT
    supabase_jwks_ttl: int = Field(3600)
    supabase_jwks_fetch_timeout: float = Field(5.0)

    # Konfiguracja serwisu lotów AeroDataBox
    flight_cache_near_expiry_minutes: int = Field(60)
    flight_cache_far_expiry_hours: int = Field(24)
    flight_cache_empty_expiry_days: int = Field(7)
    flight_cache_empty_ttl_sec: int = Field(604800)  # 7 days in seconds
    aerodatabox_api_call_interval: float = Field(1.5)
    aerodatabox_window_hours: int = Field(12)
    debug_flight_service: bool = Field(True)

    # Konfiguracja serwisu cen biletów Aviasales
    price_cache_near_expiry_minutes: int = Field(30)
    price_cache_far_expiry_hours: int = Field(6)
    price_cache_empty_ttl_hours: int = Field(24)
    aviasales_default_limit: int = Field(1000)
    debug_price_service: bool = Field(True)
    
    # Parametry sieciowe dla klientów API
    aerodatabox_base_url: str = Field("https://aerodatabox.p.rapidapi.com")
    aviasales_base_url: str = Field("https://api.travelpayouts.com/aviasales/v3/prices_for_dates")
    aerodatabox_timeout: float = Field(30.0)
    aviasales_timeout: float = Field(30.0)
    debug_api_calls: bool = Field(True)

    # Ścieżka do logów
    debug_log_file: str = Field("debug.log")

    # Domyślne preferencje wyszukiwania
    default_currency: str = Field("PLN", description="Default currency")
    default_flight_direction: str = Field("Departure", description="Default flight direction")

    # Limity zapytań (SlowAPI)
    rate_limit_flights: str = Field("50/minute")

    # Walidatory sprawdzające czy kluczowe parametry zostały poprawnie załadowane
    @field_validator('database_url')
    @classmethod
    def database_url_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('DATABASE_URL not found')
        return v

    @field_validator('aerodatabox_api_key')
    @classmethod
    def aerodatabox_api_key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('AERODATABOX_API_KEY not found')
        return v

    @field_validator('aviasales_api_token')
    @classmethod
    def aviasales_api_token_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('AVIASALES_API_TOKEN not found')
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
