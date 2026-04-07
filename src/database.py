import asyncpg
import json
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator, Any
from src.config import settings

class Database:
    # Wzorzec Singleton zapewnia jedną pulę połączeń dla całej aplikacji
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        # Inicjalizacja puli połączeń na podstawie konfiguracji i zmiennych środowiskowych
        self.pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=settings.database_pool_min_size,
            max_size=settings.database_pool_max_size,
            command_timeout=settings.database_command_timeout,
            init=self._init_connection
        )
    
    async def disconnect(self):
        # Zamknięcie puli przy zatrzymaniu serwera
        if self.pool:
            await self.pool.close()
    
    @staticmethod
    async def _init_connection(conn):
        # Automatyczne mapowanie formatu JSONB na słowniki Pythona
        await conn.set_type_codec(
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[Any, None]:
        # Wzorzec DAO oddziela operacje na bazie od logiki biznesowej
        # Pula jest tworzona leniwie (Lazy Initialization) przy pierwszym zapytaniu
        if not self.pool:
            await self.connect()
        assert self.pool is not None
        async with self.pool.acquire() as connection:
            yield connection

db = Database()