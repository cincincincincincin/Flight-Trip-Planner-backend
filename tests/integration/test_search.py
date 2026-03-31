"""
Testy integracyjne dla endpointów wyszukiwania (/search).
Używają prawdziwej bazy danych z pełnymi danymi lotniczymi.
"""


async def test_puste_zapytanie_zwraca_kraje(client):
    resp = await client.get("/search")
    assert resp.status_code == 200
    data = resp.json()
    assert data["phase"] == 1
    assert len(data["data"]) > 0
    # Każdy element to kraj z kodem
    first = data["data"][0]
    assert "code" in first
    assert "name" in first


async def test_wyszukiwanie_polski(client):
    resp = await client.get("/search", params={"q": "pol"})
    assert resp.status_code == 200
    data = resp.json()
    codes = [item["code"] for item in data["data"]]
    assert "PL" in codes


async def test_wyszukiwanie_niemiec(client):
    resp = await client.get("/search", params={"q": "ger"})
    assert resp.status_code == 200
    data = resp.json()
    codes = [item["code"] for item in data["data"]]
    assert "DE" in codes


async def test_odpowiedz_zawiera_phase_info(client):
    resp = await client.get("/search", params={"q": "ber"})
    assert resp.status_code == 200
    data = resp.json()
    assert "phase_info" in data
    phase_info = data["phase_info"]
    assert "has_phase2" in phase_info
    assert "has_phase3" in phase_info
    assert "next_phase_available" in phase_info


async def test_zapytanie_3_znaki_zawiera_exact_match(client):
    """Zapytanie o dokładny kod IATA lotniska — odpowiedź powinna zawierać exact_match."""
    resp = await client.get("/search", params={"q": "waw"})
    assert resp.status_code == 200
    data = resp.json()
    assert "exact_match" in data
    if data["exact_match"] is not None:
        assert data["exact_match"]["code"] == "WAW"


async def test_zapytanie_dluzsze_niz_3_znaki_brak_exact_match(client):
    resp = await client.get("/search", params={"q": "warsaw"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("exact_match") is None


async def test_paginacja_offset(client):
    resp1 = await client.get("/search", params={"q": "", "offset": 0, "limit": 5})
    resp2 = await client.get("/search", params={"q": "", "offset": 5, "limit": 5})
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    codes1 = {item["code"] for item in resp1.json()["data"]}
    codes2 = {item["code"] for item in resp2.json()["data"]}
    # Różne strony nie powinny zwracać tych samych krajów
    assert codes1.isdisjoint(codes2)


async def test_parametr_jezyka(client):
    resp_pl = await client.get("/search", params={"q": "pol", "lang": "pl"})
    resp_en = await client.get("/search", params={"q": "pol", "lang": "en"})
    assert resp_pl.status_code == 200
    assert resp_en.status_code == 200


async def test_pobierz_lotnisko_po_kodzie(client):
    resp = await client.get("/search/airport/WAW")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["code"] == "WAW"
    assert "name" in data["data"]


async def test_lotnisko_nieistniejace_zwraca_404(client):
    resp = await client.get("/search/airport/ZZZ")
    assert resp.status_code == 404


async def test_pobierz_miasto_po_kodzie(client):
    resp = await client.get("/search/city/WAW")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["code"] == "WAW"


async def test_search_mode_w_odpowiedzi(client):
    resp = await client.get("/search", params={"q": "war"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["search_mode"] in ("prefix", "contains")
