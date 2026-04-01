import os

# Ustaw zmienne środowiskowe PRZED jakimkolwiek importem src.*
# Pydantic Settings czyta env vars w pierwszej kolejności (przed .env)
_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://testuser:testpass@localhost:5431/flights_test",
)
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ.setdefault("AERODATABOX_API_KEY", "test_key_placeholder")
os.environ.setdefault("AVIASALES_API_TOKEN", "test_token_placeholder")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test_jwt_secret_long_enough_for_hs256_32chars!")
os.environ["REDIS_URL"] = ""  # wyłącz Redis w testach (graceful degradation)

import json
import pytest
import pytest_asyncio
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from httpx import AsyncClient, ASGITransport
from jose import jwt as jose_jwt
from datetime import datetime, timedelta, timezone

from src.main import app
from src.auth import get_current_user
from src.database import db

TEST_DB_URL = os.environ["DATABASE_URL"]
TEST_JWT_SECRET = os.environ["SUPABASE_JWT_SECRET"]
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"

# URL bazy admin (flights) — do tworzenia flights_test
_ADMIN_DB_URL = TEST_DB_URL.rsplit("/", 1)[0] + "/flights"


def _ensure_test_db() -> None:
    """Tworzy bazę flights_test jeśli nie istnieje."""
    conn = psycopg2.connect(_ADMIN_DB_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'flights_test'")
    if not cur.fetchone():
        cur.execute("CREATE DATABASE flights_test")
    cur.close()
    conn.close()


def _init_test_db() -> None:
    """Inicjalizuje schemat i dane w flights_test (idempotentne)."""
    init_dir = os.path.join(os.path.dirname(__file__), "..", "init_db")
    conn = psycopg2.connect(TEST_DB_URL)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # Sprawdź czy już zainicjalizowana
            cur.execute("SELECT to_regclass('public.countries')")
            row = cur.fetchone()
            if row is not None and row[0] is not None:
                cur.execute("SELECT COUNT(*) FROM countries")
                count_row = cur.fetchone()
                if count_row is not None and count_row[0] > 0:
                    return  # już gotowa

            with open(os.path.join(init_dir, "01_schema.sql"), encoding="utf-8") as f:
                cur.execute(f.read())

            inserts = [
                (
                    "countries.json",
                    "INSERT INTO countries (code, name, name_translations, currency, wikipedia_link)"
                    " SELECT e->>'code', e->>'name', e->'name_translations', e->>'currency', e->>'wikipedia_link'"
                    " FROM jsonb_array_elements(%s::jsonb) e",
                ),
                (
                    "cities.json",
                    "INSERT INTO cities (code, name, name_translations, country_code, time_zone, coordinates)"
                    " SELECT e->>'code', e->>'name', e->'name_translations', e->>'country_code', e->>'time_zone', e->'coordinates'"
                    " FROM jsonb_array_elements(%s::jsonb) e",
                ),
                (
                    "airlines.json",
                    "INSERT INTO airlines (code, name, name_translations, is_lowcost)"
                    " SELECT e->>'code', e->>'name', e->'name_translations', COALESCE((e->>'is_lowcost')::BOOLEAN, FALSE)"
                    " FROM jsonb_array_elements(%s::jsonb) e",
                ),
                (
                    "airports.json",
                    "INSERT INTO airports (code, name, name_translations, city_code, country_code, time_zone, coordinates, urls)"
                    " SELECT e->>'code', e->>'name', e->'name_translations', e->>'city_code', e->>'country_code',"
                    "        e->>'time_zone', e->'coordinates', e->'urls'"
                    " FROM jsonb_array_elements(%s::jsonb) e",
                ),
            ]

            init_data = os.path.join(init_dir, "init_data")
            for filename, query in inserts:
                with open(os.path.join(init_data, filename), encoding="utf-8") as f:
                    data = json.load(f)
                for i in range(0, len(data), 5000):
                    cur.execute(query, (json.dumps(data[i : i + 5000]),))

            with open(os.path.join(init_dir, "02_post_data_schema.sql"), encoding="utf-8") as f:
                cur.execute(f.read())

            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def make_test_token(user_id: str = TEST_USER_ID) -> str:
    """Tworzy prawidłowy JWT token do testów chronionych endpointów."""
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "role": "authenticated",
    }
    return jose_jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="session", autouse=True)
def init_test_database():
    """Tworzy i inicjalizuje bazę testową raz na całą sesję testów."""
    _ensure_test_db()
    _init_test_db()


@pytest_asyncio.fixture(scope="session")
async def client(init_test_database):
    """HTTP klient podłączony do aplikacji z testową bazą danych."""
    await db.connect()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:  # type: ignore
        yield ac
    await db.disconnect()


@pytest.fixture
def auth_headers():
    """Nagłówek Authorization z prawidłowym tokenem testowym."""
    return {"Authorization": f"Bearer {make_test_token()}"}


@pytest.fixture
def override_auth():
    """Nadpisuje zależność get_current_user — pomija weryfikację JWT."""
    original = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: {"sub": TEST_USER_ID}
    yield
    app.dependency_overrides = original
