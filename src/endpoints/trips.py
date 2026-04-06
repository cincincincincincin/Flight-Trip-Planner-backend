import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Path
from src.auth import get_current_user
from src.database import db
from src.models.trip import SaveTripRequest, TripResponse

logger = logging.getLogger(__name__)

# Endpointy do zarządzania zapisanymi podróżami użytkownika
# Wszystkie trasy wymagają poprawnego tokena JWT (Bearer token) z systemu Supabase

router = APIRouter(prefix="/trips", tags=["trips"])


@router.get("", response_model=list[TripResponse])
async def list_trips(user: dict = Depends(get_current_user)):
    # Pobiera listę wszystkich zapisanych podróży użytkownika
    user_id: str = user["sub"]
    async with db.get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, user_id, name, trip_state, trip_routes, created_at, updated_at
            FROM user_trips
            WHERE user_id = $1
            ORDER BY updated_at DESC
            """,
            user_id,
        )
    return [
        {
            "id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "trip_state": json.loads(row["trip_state"]) if isinstance(row["trip_state"], str) else row["trip_state"],
            "trip_routes": json.loads(row["trip_routes"]) if isinstance(row["trip_routes"], str) else row["trip_routes"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


@router.post("", response_model=TripResponse, status_code=201)
async def save_trip(body: SaveTripRequest, user: dict = Depends(get_current_user)):
    # Zapisuje nową podróż użytkownika
    user_id: str = user["sub"]
    async with db.get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO user_trips (user_id, name, trip_state, trip_routes)
            VALUES ($1, $2, $3::jsonb, $4::jsonb)
            RETURNING id, user_id, name, trip_state, trip_routes, created_at, updated_at
            """,
            user_id,
            body.name,
            json.dumps(body.trip_state.model_dump()),
            json.dumps(body.trip_routes),
        )
    assert row is not None
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "trip_state": json.loads(row["trip_state"]) if isinstance(row["trip_state"], str) else row["trip_state"],
        "trip_routes": json.loads(row["trip_routes"]) if isinstance(row["trip_routes"], str) else row["trip_routes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.put("/{trip_id}", response_model=TripResponse)
async def update_trip(
    body: SaveTripRequest,
    trip_id: int = Path(...),
    user: dict = Depends(get_current_user),
):
    # Aktualizuje istniejącą podróż użytkownika
    user_id: str = user["sub"]
    async with db.get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE user_trips
            SET name = $1, trip_state = $2::jsonb, trip_routes = $3::jsonb, updated_at = NOW()
            WHERE id = $4 AND user_id = $5
            RETURNING id, user_id, name, trip_state, trip_routes, created_at, updated_at
            """,
            body.name,
            json.dumps(body.trip_state.model_dump()),
            json.dumps(body.trip_routes),
            trip_id,
            user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Trip not found or access denied")
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "trip_state": json.loads(row["trip_state"]) if isinstance(row["trip_state"], str) else row["trip_state"],
        "trip_routes": json.loads(row["trip_routes"]) if isinstance(row["trip_routes"], str) else row["trip_routes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.delete("/{trip_id}", status_code=204)
async def delete_trip(
    trip_id: int = Path(...),
    user: dict = Depends(get_current_user),
):
    # Usuwa podróż użytkownika
    user_id: str = user["sub"]
    async with db.get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM user_trips WHERE id = $1 AND user_id = $2",
            trip_id,
            user_id,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Trip not found or access denied")
