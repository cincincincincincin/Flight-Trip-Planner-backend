from pydantic import BaseModel
from typing import Any, Dict

# Modele obsługujące ustawienia systemowe i wizualne użytkownika

class SettingsPrefs(BaseModel):
    # Parametry konfiguracyjne (język, waluta, limity przesiadek)
    language: str
    currency: str
    min_transfer_hours: float
    min_manual_transfer_hours: float
    show_refresh_button: bool
    show_console_logs: bool

class MapPrefs(BaseModel):
    # Ustawienia wizualne mapy (styl, tryb globusa)
    map_style: str
    globe_mode: bool

class PreferencesData(BaseModel):
    # Zbiorcza struktura wszystkich ustawień i kolorów
    settings: SettingsPrefs
    map: MapPrefs
    colors: Dict[str, Any]

class PreferencesPayload(BaseModel):
    # Żądanie zapisu nowych ustawień
    data: PreferencesData

class PreferencesResponse(BaseModel):
    # Odpowiedź API z aktualnymi ustawieniami
    data: PreferencesData
