"""
Integration tests for GET /flights/airport/{airport_code}.
Tests focus on parameter validation and to_local_datetime support.
No external API calls — tests use the endpoint without forcing refresh.
"""
import pytest


@pytest.mark.asyncio
async def test_flights_endpoint_returns_200_without_params(client):
    resp = await client.get("/flights/airport/WAW")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "data" in data
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_flights_endpoint_accepts_from_local_datetime(client):
    resp = await client.get(
        "/flights/airport/WAW",
        params={"from_local_datetime": "2026-04-05T08:00:00"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_flights_endpoint_accepts_to_local_datetime(client):
    resp = await client.get(
        "/flights/airport/WAW",
        params={
            "from_local_datetime": "2026-04-05T08:00:00",
            "to_local_datetime": "2026-04-06T02:00:00",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_flights_endpoint_invalid_from_datetime_returns_400(client):
    resp = await client.get(
        "/flights/airport/WAW",
        params={"from_local_datetime": "not-a-datetime"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_flights_endpoint_invalid_to_datetime_returns_400(client):
    resp = await client.get(
        "/flights/airport/WAW",
        params={
            "from_local_datetime": "2026-04-05T08:00:00",
            "to_local_datetime": "not-a-datetime",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_flights_response_has_required_fields(client):
    resp = await client.get("/flights/airport/WAW")
    assert resp.status_code == 200
    data = resp.json()
    assert "success" in data
    assert "data" in data
    assert "count" in data
    assert "range_end_datetime" in data
