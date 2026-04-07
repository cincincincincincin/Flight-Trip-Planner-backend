import json
import logging
from typing import Any, Optional, Callable, Awaitable
import redis.asyncio as aioredis
from pydantic import BaseModel
from src.config import settings

# Klasa pomocnicza która rozszerza standardowy koder JSON o obsługę modeli Pydantic
# Pozwala to na automatyczną zamianę obiektów danych na tekst który może być zapisany w Redisie
class _PydanticEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, BaseModel):
            return o.model_dump()
        return super().default(o)

logger = logging.getLogger(__name__)

# System pamięci podręcznej wykorzystujący bazę Redis która przechowuje dane w pamięci RAM
# Zastosowany wzorzec Cache-Aside polega na tym że aplikacja najpierw sprawdza cache
# a dopiero gdy tam nie ma danych to odpytuje bazę postgres i uzupełnia brakujący wpis
class RedisCache:
    def __init__(self):
        self._client: Optional[aioredis.Redis] = None

    async def connect(self):
        # Inicjalizacja połączenia oraz sprawdzenie dostępności serwera Redis
        try:
            self._client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=settings.redis_connect_timeout,
                socket_timeout=settings.redis_socket_timeout,
            )
            await self._client.ping()
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.warning(f"Redis unavailable (cache disabled): {e}")
            self._client = None

    @property
    def is_ready(self) -> bool:
        # Informuje czy system cache jest aktualnie dostępny
        return self._client is not None

    def get_lock(self, name: str, timeout: float = 10.0) -> Any:
        # Zwraca obiekt blokady rozproszonej Redis, jeśli klient jest połączony
        if self._client:
            return self._client.lock(f"lock:{name}", timeout=timeout)
        return None

    async def disconnect(self):
        # Zamykanie aktywnej sesji podczas kończenia pracy przez serwer
        if self._client:
            await self._client.aclose()
            logger.info("Redis disconnected")

    async def get(self, key: str) -> Optional[Any]:
        # Pobieranie danych dla konkretnego klucza lub None w przypadku braku danych lub błędu
        if not self._client:
            return None
        try:
            raw = await self._client.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception as e:
            logger.warning(f"Redis GET error for '{key}': {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        # Zapis danych w cache z określonym czasem ważności TTL
        if not self._client:
            return
        try:
            await self._client.set(key, json.dumps(value, cls=_PydanticEncoder), ex=ttl)
        except Exception as e:
            logger.warning(f"Redis SET error for '{key}': {e}")

    async def cached(self, key: str, ttl: int, fn: Callable[[], Awaitable[Any]]) -> Any:
        # Funkcja, która automatycznie sprawdza cache i pobiera dane jeśli ich brakuje
        hit = await self.get(key)
        if hit is not None:
            logger.debug(f"Cache HIT: {key}")
            return hit
        
        logger.debug(f"Cache MISS: {key}")
        result = await fn()
        await self.set(key, result, ttl)
        return result

# Jeden wspólny obiekt obsługujący pamięć podręczną w całym projekcie
cache = RedisCache()
