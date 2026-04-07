import json
import logging
from typing import Dict, Any, Optional
from src.database import db
from src.models.preference import PreferencesPayload

logger = logging.getLogger(__name__)

class PreferenceService:
    # Serwis do zarządzania preferencjami użytkownika (waluta, motyw itp.)

    @staticmethod
    async def get_preferences(user_id: str) -> Optional[Dict[str, Any]]:
        # Pobiera zapisane ustawienia użytkownika z bazy danych
        async with db.get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM user_preferences WHERE user_id = $1",
                user_id,
            )
        if row is None:
            return None
        return json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]

    @staticmethod
    async def save_preferences(user_id: str, data: Dict[str, Any]) -> None:
        # Zapisuje lub aktualizuje preferencje użytkownika (operacja Upsert)
        async with db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO user_preferences (user_id, data, updated_at)
                VALUES ($1, $2::jsonb, NOW())
                ON CONFLICT (user_id) DO UPDATE
                  SET data = EXCLUDED.data,
                      updated_at = NOW()
                """,
                user_id,
                json.dumps(data),
            )

# Globalna instancja serwisu preferencji
preference_service = PreferenceService()
