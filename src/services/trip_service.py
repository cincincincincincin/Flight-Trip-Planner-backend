import json
import logging
from typing import List, Dict, Any, Optional
from src.database import db
from src.models.trip import SaveTripRequest, TripResponse

logger = logging.getLogger(__name__)

class TripService:
    # Serwis do zarządzania zapisanymi podróżami użytkowników

    @staticmethod
    async def list_trips(user_id: str) -> List[Dict[str, Any]]:
        # Pobiera listę wszystkich zapisanych tras danego użytkownika z bazy
        async with db.get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_id, name, trip_state
                FROM user_trips
                WHERE user_id = $1
                ORDER BY created_at DESC
                """,
                user_id,
            )
        return [
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "name": row["name"],
                "trip_state": json.loads(row["trip_state"]) if isinstance(row["trip_state"], str) else row["trip_state"],
            }
            for row in rows
        ]

    @staticmethod
    async def save_trip(user_id: str, body: SaveTripRequest) -> Dict[str, Any]:
        # Zapisuje nową trasę użytkownika w bazie danych
        async with db.get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO user_trips (user_id, name, trip_state)
                VALUES ($1, $2, $3::jsonb)
                RETURNING id, user_id, name, trip_state
                """,
                user_id,
                body.name,
                json.dumps(body.trip_state.model_dump()),
            )
        assert row is not None
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "trip_state": json.loads(row["trip_state"]) if isinstance(row["trip_state"], str) else row["trip_state"],
        }

    @staticmethod
    async def update_trip(user_id: str, trip_id: int, body: SaveTripRequest) -> Optional[Dict[str, Any]]:
        # Aktualizuje nazwę lub zawartość istniejącej już podróży
        async with db.get_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE user_trips
                SET name = $1, trip_state = $2::jsonb, updated_at = NOW()
                WHERE id = $3 AND user_id = $4
                RETURNING id, user_id, name, trip_state
                """,
                body.name,
                json.dumps(body.trip_state.model_dump()),
                trip_id,
                user_id,
            )
        if not row:
            return None
            
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "trip_state": json.loads(row["trip_state"]) if isinstance(row["trip_state"], str) else row["trip_state"],
        }

    @staticmethod
    async def delete_trip(user_id: str, trip_id: int) -> bool:
        # Usuwa wpis o podróży z bazy danych
        async with db.get_connection() as conn:
            result = await conn.execute(
                "DELETE FROM user_trips WHERE id = $1 AND user_id = $2",
                trip_id,
                user_id,
            )
        return result != "DELETE 0"

# Globalny obiekt serwisu podróży
trip_service = TripService()
