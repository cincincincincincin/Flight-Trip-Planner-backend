import logging
import time
from typing import Optional
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from src.config import settings

logger = logging.getLogger(__name__)

# Integracja z systemem Supabase służąca do weryfikacji tożsamości użytkowników przy pomocy podpisanych tokenów JWT
# System obsługuje dwa sposoby sprawdzania podpisu czyli algorytm symetryczny HS256
# oraz asymetryczny RS256 pobierający klucze publiczne z adresu JWKS

# Podręczna kopia kluczy publicznych która jest ważna przez godzinę w celu ograniczenia liczby zapytań
_jwks_cache: Optional[dict] = None
_jwks_fetched_at: float = 0.0
JWKS_TTL_SECONDS = settings.supabase_jwks_ttl

bearer_scheme = HTTPBearer(auto_error=False)


async def _get_jwks() -> Optional[dict]:
    # Pobieranie i zapisywanie kluczy publicznych Supabase potrzebnych do weryfikacji asymetrycznej
    # Zwraca None w przypadku braku adresu URL serwera auth
    global _jwks_cache, _jwks_fetched_at

    if not settings.supabase_url:
        return None

    now = time.monotonic()
    if _jwks_cache and (now - _jwks_fetched_at) < JWKS_TTL_SECONDS:
        return _jwks_cache

    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        async with httpx.AsyncClient(timeout=settings.supabase_jwks_fetch_timeout) as client:
            resp = await client.get(jwks_url)
            resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = now
        logger.info("JWKS fetched successfully from Supabase")
        return _jwks_cache
    except Exception as e:
        logger.warning(f"Failed to fetch JWKS: {e}")
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    # Funkcja używana jako zależność w routerach FastAPI która sprawdza czy użytkownik przysłał ważny token
    # Wykorzystuje metodę HS256 jako priorytetową oraz RS256 jako rozwiązanie zapasowe
    # Zgłasza wyjątek HTTP 401 w przypadku braku lub niepoprawności tokena
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Próba weryfikacji algorytmem HS256 przy użyciu sekretnego klucza JWT
    if settings.supabase_jwt_secret:
        try:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                # Pominięcie sprawdzania pola audytorium ze względu na domyślną konfigurację systemu Supabase
                # Bezpieczeństwo jest zapewnione przez weryfikację podpisu SUPABASE_JWT_SECRET
                options={"verify_aud": False},
            )
            return payload
        except JWTError as e:
            logger.debug(f"HS256 verification failed: {e}")

    # Próba weryfikacji algorytmem RS256/ES256 przy użyciu kluczy publicznych JWKS
    try:
        jwks = await _get_jwks()
        if jwks:
            payload = jwt.decode(
                token,
                jwks,
                algorithms=["RS256", "ES256"],
                options={"verify_aud": False},
            )
            return payload
    except Exception as e:
        logger.debug(f"RS256 verification failed: {e}")

    logger.warning("JWT verification failed: all methods exhausted")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
