"""
Testy integracyjne dla endpointów podróży (/trips).
Chronione endpointy wymagają JWT — w testach nadpisujemy get_current_user.
"""
import pytest

_TRIP_PAYLOAD = {
    "name": "Testowa podróż",
    "trip_state": {
        "startAirport": {"code": "WAW", "city_code": "WAW", "country_code": "PL"},
        "legs": [],
    },
    "trip_routes": [],
}


async def test_lista_podrozy_wymaga_autoryzacji(client):
    resp = await client.get("/trips")
    assert resp.status_code == 401


async def test_lista_podrozy_z_autoryzacja(client, override_auth):
    resp = await client.get("/trips", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_tworzenie_podrozy(client, override_auth):
    resp = await client.post(
        "/trips",
        json=_TRIP_PAYLOAD,
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Testowa podróż"
    assert "id" in data
    assert "created_at" in data


async def test_tworzenie_podrozy_bez_autoryzacji(client):
    resp = await client.post("/trips", json=_TRIP_PAYLOAD)
    assert resp.status_code == 401


async def test_aktualizacja_podrozy(client, override_auth):
    create_resp = await client.post(
        "/trips",
        json=_TRIP_PAYLOAD,
        headers={"Authorization": "Bearer fake"},
    )
    trip_id = create_resp.json()["id"]

    updated_payload = {**_TRIP_PAYLOAD, "name": "Zaktualizowana podróż"}
    resp = await client.put(
        f"/trips/{trip_id}",
        json=updated_payload,
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Zaktualizowana podróż"


async def test_aktualizacja_cudzej_podrozy_zwraca_404(client, override_auth):
    resp = await client.put(
        "/trips/99999",
        json=_TRIP_PAYLOAD,
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 404


async def test_usuniecie_podrozy(client, override_auth):
    create_resp = await client.post(
        "/trips",
        json=_TRIP_PAYLOAD,
        headers={"Authorization": "Bearer fake"},
    )
    trip_id = create_resp.json()["id"]

    resp = await client.delete(
        f"/trips/{trip_id}",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 204


async def test_usuniecie_nieistniejacych_podrozy_zwraca_404(client, override_auth):
    resp = await client.delete(
        "/trips/99999",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 404


async def test_usunieta_podroz_znika_z_listy(client, override_auth):
    create_resp = await client.post(
        "/trips",
        json=_TRIP_PAYLOAD,
        headers={"Authorization": "Bearer fake"},
    )
    trip_id = create_resp.json()["id"]

    await client.delete(f"/trips/{trip_id}", headers={"Authorization": "Bearer fake"})

    list_resp = await client.get("/trips", headers={"Authorization": "Bearer fake"})
    ids = [t["id"] for t in list_resp.json()]
    assert trip_id not in ids


async def test_trip_state_zapisywany_i_odczytywany(client, override_auth):
    payload = {
        **_TRIP_PAYLOAD,
        "trip_state": {
            "startAirport": {"code": "KRK", "city_code": "KRK", "country_code": "PL"},
            "legs": [
                {
                    "fromAirportCode": "KRK",
                    "toAirportCode": "WAW",
                    "type": "flight",
                    "flight": None,
                }
            ],
        },
    }
    create_resp = await client.post(
        "/trips",
        json=payload,
        headers={"Authorization": "Bearer fake"},
    )
    assert create_resp.status_code == 201
    trip_state = create_resp.json()["trip_state"]
    assert trip_state["startAirport"]["code"] == "KRK"
    assert len(trip_state["legs"]) == 1
