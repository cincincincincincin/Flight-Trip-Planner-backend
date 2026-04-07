import logging
from fastapi import APIRouter, Depends, HTTPException, Path
from src.auth import get_current_user
from src.services.trip_service import trip_service
from src.models.trip import SaveTripRequest, TripResponse

logger = logging.getLogger(__name__)

# Endpointy do zarządzania zapisanymi podróżami użytkownika
# Dostęp tylko dla zalogowanych użytkowników (wymagany token JWT)
router = APIRouter(prefix="/trips", tags=["trips"])

@router.get("", response_model=list[TripResponse])
async def list_trips(user: dict = Depends(get_current_user)):
    # Pobiera listę zapisanych podróży zalogowanego użytkownika
    user_id: str = user["sub"]
    return await trip_service.list_trips(user_id)

@router.post("", response_model=TripResponse, status_code=201)
async def save_trip(body: SaveTripRequest, user: dict = Depends(get_current_user)):
    # Zapisuje nową podróż użytkownika
    user_id: str = user["sub"]
    return await trip_service.save_trip(user_id, body)

@router.put("/{trip_id}", response_model=TripResponse)
async def update_trip(
    body: SaveTripRequest,
    trip_id: int = Path(...),
    user: dict = Depends(get_current_user),
):
    # Aktualizuje istniejącą podróż użytkownika
    user_id: str = user["sub"]
    trip = await trip_service.update_trip(user_id, trip_id, body)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found or access denied")
    return trip

@router.delete("/{trip_id}", status_code=204)
async def delete_trip(
    trip_id: int = Path(...),
    user: dict = Depends(get_current_user),
):
    # Usuwa podróż użytkownika
    user_id: str = user["sub"]
    success = await trip_service.delete_trip(user_id, trip_id)
    if not success:
        raise HTTPException(status_code=404, detail="Trip not found or access denied")
