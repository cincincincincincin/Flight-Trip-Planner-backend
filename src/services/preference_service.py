import json
import logging
from typing import Dict, Any, Optional
from src.database import db
from src.models.preference import PreferencesPayload

logger = logging.getLogger(__name__)

class PreferenceService:
    """Service for managing user's search and display preferences."""

    @staticmethod
    async def get_preferences(user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves user's saved preferences."""
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
        """Saves or updates user's preferences (Upsert)."""
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

# Global instance
preference_service = PreferenceService()
