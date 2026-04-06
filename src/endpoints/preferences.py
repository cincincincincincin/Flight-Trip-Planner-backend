import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from src.auth import get_current_user
from src.database import db
from src.models.preference import PreferencesPayload, PreferencesResponse

logger = logging.getLogger(__name__)

# Endpointy obsługujące preferencje użytkownika
# Dostęp wymaga dostarczenia poprawnego tokenu Supabase JWT (Bearer)

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=PreferencesResponse)
async def get_preferences(user: dict = Depends(get_current_user)):
    # Pobiera aktualne ustawienia i preferencje użytkownika
    user_id: str = user["sub"]
    async with db.get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT data FROM user_preferences WHERE user_id = $1",
            user_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="No preferences saved")
    data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
    return {"data": data}


@router.put("", response_model=PreferencesResponse)
async def save_preferences(body: PreferencesPayload, user: dict = Depends(get_current_user)):
    # Zapisuje lub aktualizuje preferencje użytkownika
    user_id: str = user["sub"]
    data_json = body.data.model_dump()
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
            json.dumps(data_json),
        )
    return {"data": data_json}
