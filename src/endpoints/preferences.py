import logging
from fastapi import APIRouter, Depends, HTTPException
from src.auth import get_current_user
from src.services.preference_service import preference_service
from src.models.preference import PreferencesPayload, PreferencesResponse

logger = logging.getLogger(__name__)

# Endpointy obsługujące preferencje użytkownika
# Dostęp wymaga dostarczenia poprawnego tokenu Supabase JWT (Bearer)

router = APIRouter(prefix="/preferences", tags=["preferences"])

@router.get("", response_model=PreferencesResponse)
async def get_preferences(user: dict = Depends(get_current_user)):
    # Pobiera aktualne ustawienia i preferencje użytkownika
    user_id: str = user["sub"]
    data = await preference_service.get_preferences(user_id)
    if data is None:
        raise HTTPException(status_code=404, detail="No preferences saved")
    return {"data": data}

@router.put("", response_model=PreferencesResponse)
async def save_preferences(body: PreferencesPayload, user: dict = Depends(get_current_user)):
    # Zapisuje lub aktualizuje preferencje użytkownika
    user_id: str = user["sub"]
    data_dict = body.data.model_dump()
    await preference_service.save_preferences(user_id, data_dict)
    return {"data": data_dict}
