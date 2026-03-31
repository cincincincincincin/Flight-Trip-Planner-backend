"""
Testy jednostkowe dla funkcji filter_outliers z search_service.

filter_outliers iteracyjnie usuwa punkty oddalone o więcej niż max_degrees
od mediany, zwracając współrzędne głównego skupiska.
"""
from src.services.search_service import filter_outliers


def test_pusta_lista():
    assert filter_outliers([]) == []


def test_pojedynczy_punkt():
    assert filter_outliers([(10.0, 50.0)]) == [(10.0, 50.0)]


def test_dwa_punkty_blisko_siebie():
    coords = [(0.0, 0.0), (1.0, 1.0)]
    result = filter_outliers(coords, max_degrees=5.0)
    assert len(result) == 2


def test_brak_outlierow():
    coords = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0), (1.5, 0.5)]
    result = filter_outliers(coords, max_degrees=5.0)
    assert len(result) == 4


def test_usuwa_odlegly_punkt():
    # Skupisko wokół (0, 0), jeden outlier daleko
    coords = [(0.0, 0.0), (1.0, 0.5), (0.5, 1.0), (100.0, 0.0)]
    result = filter_outliers(coords, max_degrees=5.0)
    assert (100.0, 0.0) not in result
    assert len(result) == 3


def test_zachowuje_glowne_skupisko():
    cluster = [(float(i * 0.5), float(i * 0.5)) for i in range(8)]  # skupisko ~(0-3.5, 0-3.5)
    outlier = [(50.0, 50.0)]
    result = filter_outliers(cluster + outlier, max_degrees=5.0)
    assert (50.0, 50.0) not in result
    assert len(result) == len(cluster)


def test_nie_zwraca_pustej_listy():
    # Nawet jeśli wszystkie punkty są daleko od siebie, funkcja nie powinna zwrócić []
    coords = [(0.0, 0.0), (100.0, 0.0)]
    result = filter_outliers(coords, max_degrees=5.0)
    assert len(result) > 0


def test_symetria_wzgledem_mediany():
    # Cztery rogi kwadratu 2x2 — żaden nie jest outlierem przy max_degrees=3
    coords = [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0), (2.0, 2.0)]
    result = filter_outliers(coords, max_degrees=3.0)
    assert len(result) == 4


def test_iteracyjne_usuwanie():
    # Pierwszy przebieg usuwa jeden outlier, drugi przebieg może usunąć kolejny
    coords = [
        (0.0, 0.0), (1.0, 0.0), (0.5, 0.5),  # skupisko
        (8.0, 0.0),   # zostaje usunięty w 1. przebiegu
        (15.0, 0.0),  # zostaje usunięty w 2. przebiegu (po usunięciu (8,0))
    ]
    result = filter_outliers(coords, max_degrees=3.0)
    assert (15.0, 0.0) not in result


def test_zachowanie_dla_kolizji():
    # Dwa identyczne punkty tworzą skupisko
    coords = [(5.0, 5.0), (5.0, 5.0), (5.0, 5.0), (100.0, 100.0)]
    result = filter_outliers(coords, max_degrees=1.0)
    assert (100.0, 100.0) not in result
    assert len(result) == 3
