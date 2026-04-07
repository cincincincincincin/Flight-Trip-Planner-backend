import logging
import time
from typing import Optional
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from src.config import settings

logger = logging.getLogger(__name__)

# Weryfikacja użytkowników Supabase przez tokeny JWT.
# Obsługujemy dwa algorytmy: HS256 (klucz symetryczny) oraz RS256 (klucze publiczne z JWKS).

# Cache kluczy publicznych
_jwks_cache: Optional[dict] = None
_jwks_fetched_at: float = 0.0
JWKS_TTL_SECONDS = settings.supabase_jwks_ttl

bearer_scheme = HTTPBearer(auto_error=False)


async def _get_jwks() -> Optional[dict]:
    # Pobieranie aktualnych kluczy publicznych z serwera Supabase dla weryfikacji RS256.
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
    # Zależność FastAPI sprawdzająca ważność tokena
    # Wykorzystuje HS256 oraz RS256 jako fallback
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Weryfikacja algorytmem HS256 przy użyciu klucza JWT_SECRET
    if settings.supabase_jwt_secret:
        try:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                # Supabase domyślnie ustawia aud na 'authenticated', więc wyłączamy jego sprawdzanie.
                # Sam podpis tokena unikalnym kluczem daje nam wystarczającą pewność.
                options={"verify_aud": False},
            )
            return payload
        except JWTError as e:
            logger.debug(f"HS256 verification failed: {e}")

    # Jeśli HS256 zawiedzie, próbujemy asymetrycznego RS256/ES256 z kluczami JWKS.
    try:
        jwks = await _get_jwks()
        if jwks:
            payload = jwt.decode(
                token,
                jwks,
                algorithms=["RS256", "ES256"],
                # Tutaj też odpuszczamy 'aud', bo klucze publiczne potwierdzają pochodzenie tokena.
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
