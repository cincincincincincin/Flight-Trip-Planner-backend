"""
Testy jednostkowe dla FlightPriceService._parse_offer_from_api.

Metoda parsuje surową odpowiedź z API Aviasales i zwraca słownik
gotowy do zapisu do bazy danych, albo None jeśli oferta jest nieprawidłowa.
"""
from datetime import date
from src.services.flight_price_service import FlightPriceService


def _raw_offer(**overrides) -> dict:
    """Buduje przykładową ofertę z API z możliwością nadpisania pól."""
    base = {
        "origin_airport": "WAW",
        "destination_airport": "CDG",
        "price": 199.0,
        "departure_at": "2024-06-15T10:00:00Z",
        "transfers": 0,
        "airline": "LO",
        "flight_number": "LO301",
        "link": "/booking/LO301",
        "duration": 180,
        "duration_to": 180,
        "duration_back": None,
        "return_transfers": 0,
    }
    base.update(overrides)
    return base


def test_parsuje_prawidlowa_oferte():
    offer = FlightPriceService._parse_offer_from_api(
        _raw_offer(), "WAW", "CDG", date(2024, 6, 15)
    )
    assert offer is not None
    assert offer["origin_airport_code"] == "WAW"
    assert offer["destination_airport_code"] == "CDG"
    assert offer["price"] == 199.0
    assert offer["transfers"] == 0
    assert offer["airline_code"] == "LO"
    assert offer["flight_number"] == "LO301"


def test_pomija_loty_z_przesiadkami():
    offer = FlightPriceService._parse_offer_from_api(
        _raw_offer(transfers=1), "WAW", "CDG", date(2024, 6, 15)
    )
    assert offer is None


def test_pomija_brak_ceny():
    offer = FlightPriceService._parse_offer_from_api(
        _raw_offer(price=None), "WAW", "CDG", date(2024, 6, 15)
    )
    assert offer is None


def test_pomija_brak_lotniska_wylotu():
    offer = FlightPriceService._parse_offer_from_api(
        _raw_offer(origin_airport=None), "WAW", "CDG", date(2024, 6, 15)
    )
    assert offer is None


def test_pomija_brak_lotniska_przylotu():
    offer = FlightPriceService._parse_offer_from_api(
        _raw_offer(destination_airport=None), "WAW", "CDG", date(2024, 6, 15)
    )
    assert offer is None


def test_pomija_brak_czasu_wylotu():
    offer = FlightPriceService._parse_offer_from_api(
        _raw_offer(departure_at=None), "WAW", "CDG", date(2024, 6, 15)
    )
    assert offer is None


def test_waluta_zamieniana_na_duze_litery():
    offer = FlightPriceService._parse_offer_from_api(
        _raw_offer(), "WAW", "CDG", date(2024, 6, 15), currency="pln"
    )
    assert offer is not None
    assert offer["currency"] == "PLN"


def test_domyslna_waluta():
    offer = FlightPriceService._parse_offer_from_api(
        _raw_offer(), "WAW", "CDG", date(2024, 6, 15)
    )
    assert offer is not None
    assert offer["currency"] is not None


def test_zwraca_None_przy_wyjatku_parsowania():
    # Nieprawidłowy format daty — powoduje wyjątek w fromisoformat
    offer = FlightPriceService._parse_offer_from_api(
        _raw_offer(departure_at="nie-jest-data"), "WAW", "CDG", date(2024, 6, 15)
    )
    assert offer is None


def test_data_wyszukiwania_zapisana():
    search_date = date(2024, 6, 15)
    offer = FlightPriceService._parse_offer_from_api(
        _raw_offer(), "WAW", "CDG", search_date
    )
    assert offer is not None
    assert offer["search_date"] == search_date


def test_kody_miast_zapisane():
    offer = FlightPriceService._parse_offer_from_api(
        _raw_offer(), "WAW", "PAR", date(2024, 6, 15)
    )
    assert offer is not None
    assert offer["origin_city_code"] == "WAW"
    assert offer["destination_city_code"] == "PAR"
