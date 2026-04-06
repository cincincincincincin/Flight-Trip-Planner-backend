import asyncpg
import json
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator, Any
from src.config import settings

class Database:
    # Zarządzanie bazą danych oparte na wzorzec Singleton który polega na tym,
    # że w całym programie istnieje tylko jeden obiekt tej klasy dzięki czemu
    # wszystkie moduły korzystają z tej samej puli połączeń

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        # Ustawienie puli połączeń na podstawie url z pliku env
        # oraz parametrów z pliku config
        self.pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=settings.database_pool_min_size,
            max_size=settings.database_pool_max_size,
            command_timeout=settings.database_command_timeout,
            init=self._init_connection
        )
    
    async def disconnect(self):
        # Zamknięcie puli i wszystkich aktywnych sesji w momencie gdy
        # serwer kończy swoją pracę
        if self.pool:
            await self.pool.close()
    
    @staticmethod
    async def _init_connection(conn):
        # Skonfigurowanie sterownika bazy tak żeby automatycznie zamieniał
        # format jsonb na słowniki pythona co pozwala uniknąć ręcznej konwersji
        await conn.set_type_codec(
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[Any, None]:
        # Wykorzystanie wzorca Data Access Object który służy do oddzielenia
        # operacji na bazie danych od reszty kodu dzięki czemu funkcje logiki
        # biznesowej nie muszą wiedzieć jak dokładnie wyglądają zapytania sql
        # Mechanizm który sprawdza czy pula połączeń już istnieje
        # i tworzy ją tylko wtedy gdy jest faktycznie potrzebna
        if not self.pool:
            await self.connect()
        assert self.pool is not None
        async with self.pool.acquire() as connection:
            yield connection

db = Database()