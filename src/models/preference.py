from pydantic import BaseModel
from typing import Any, Dict

# Modele Pydantic obsługujące preferencje systemowe i wizualne użytkownika

class SettingsPrefs(BaseModel):
    # Parametry konfiguracyjne aplikacji (język, waluta, limity czasowe przesiadek)
    language: str
    currency: str
    min_transfer_hours: float
    min_manual_transfer_hours: float
    show_refresh_button: bool
    show_console_logs: bool

class MapPrefs(BaseModel):
    # Ustawienia wizualizacji geograficznej (styl mapy, tryb globusa)
    map_style: str
    globe_mode: bool

class PreferencesData(BaseModel):
    # Zbiorcza struktura danych zawierająca ustawienia, ustawienia mapy oraz stan kolorystyki
    settings: SettingsPrefs
    map: MapPrefs
    colors: Dict[str, Any]  # Nieprzezroczysty stan synchronizowany z colorStore

class PreferencesPayload(BaseModel):
    # Model żądania zapisu preferencji wysyłany z frontendowej warstwy aplikacji
    data: PreferencesData

class PreferencesResponse(BaseModel):
    # Model odpowiedzi serwera dostarczający kompletny zestaw preferencji użytkownika
    data: PreferencesData
