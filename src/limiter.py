import redis
from slowapi import Limiter
from slowapi.util import get_remote_address
from src.config import settings
import logging

logger = logging.getLogger(__name__)

def _get_storage_uri() -> str:
    # Automatyczne przełączanie między Redis
    # a pamięcią lokalną
    
    if not settings.redis_url:
        # Wykorzystanie lokalnej pamięci programu
        return "memory://"
    
    try:
        # Sprawdzanie dostępności poprzez ping
        client = redis.from_url(settings.redis_url, socket_connect_timeout=1)
        if client is not None:
            client.ping()
            return settings.redis_url
    except Exception as e:
        # Przełączenie w tryb awaryjny
        logger.warning(f"Redis unreachable for Rate Limiter ({e}). Falling back to 'memory://' storage.")
    
    return "memory://"

# System ograniczania liczby zapytań
# Wykorzystuje adres IP użytkownika jako klucz identyfikacyjny
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_get_storage_uri()
)
