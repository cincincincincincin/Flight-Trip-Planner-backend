from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from src.config import settings
from src.database import db
from src.cache import cache
from src.limiter import limiter
from src.endpoints.flights import router as flights_router
from src.endpoints.trips import router as trips_router
from src.endpoints.preferences import router as preferences_router
import logging

# Konfiguracja logowania
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.debug_log_file, encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Obsługa startu i wyłączania serwera
    logger.info("Starting up...")
    try:
        await db.connect()
        logger.info("Database connected successfully")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

    # Redis jest opcjonalny błąd cache'u nie powinien blokować startu
    await cache.connect()

    yield

    logger.info("Shutting down...")
    await db.disconnect()
    await cache.disconnect()
    logger.info("Database disconnected")


# Inicjalizacja FastAPI
app = FastAPI(
    title=settings.app_name,
    description="API for flight trip planner app",
    version="1.0.0",
    lifespan=lifespan,
    debug=settings.debug,
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]


# Handlery wyjątków

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error on {request.url}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"success": False, "error": "Validation error", "details": exc.errors()},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"},
    )


# Middleware CORS (pozwalamy frontendowi na dostęp)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpointy API (Routery)

app.include_router(flights_router)
app.include_router(trips_router)
app.include_router(preferences_router)

@app.get("/")
async def root():
    return {
        "message": "Flight Map API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "flights": "/flights",
            "trips": "/trips",
        },
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
