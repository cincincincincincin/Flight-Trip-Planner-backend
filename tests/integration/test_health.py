"""
Testy integracyjne dla endpointów diagnostycznych.
"""


async def test_health_zwraca_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


async def test_root_zwraca_info_o_api(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "endpoints" in data
    assert "search" in data["endpoints"]
    assert "trips" in data["endpoints"]
