"""
Modele Pydantic dla endpointu preferencji użytkownika.
"""
from pydantic import BaseModel
from typing import Any, Dict


class SettingsPrefs(BaseModel):
    language: str
    currency: str
    min_transfer_hours: float
    min_manual_transfer_hours: float
    show_refresh_button: bool
    show_console_logs: bool


class MapPrefs(BaseModel):
    map_style: str
    globe_mode: bool


class PreferencesData(BaseModel):
    settings: SettingsPrefs
    map: MapPrefs
    colors: Dict[str, Any]  # nieprzezroczysty stan colorStore


class PreferencesPayload(BaseModel):
    data: PreferencesData


class PreferencesResponse(BaseModel):
    data: PreferencesData
