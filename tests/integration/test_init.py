"""
Integration tests for the /init endpoint.
"""
import pytest


@pytest.mark.asyncio
async def test_init_returns_both_datasets(client):
    resp = await client.get("/init")
    assert resp.status_code == 200
    data = resp.json()
    assert "geojson" in data
    assert "country_centers" in data


@pytest.mark.asyncio
async def test_init_geojson_is_feature_collection(client):
    resp = await client.get("/init")
    assert resp.status_code == 200
    geojson = resp.json()["geojson"]
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) > 0


@pytest.mark.asyncio
async def test_init_geojson_features_have_required_props(client):
    resp = await client.get("/init")
    assert resp.status_code == 200
    props = resp.json()["geojson"]["features"][0]["properties"]
    assert "code" in props
    assert "name" in props
    assert "country_code" in props
    assert "time_zone" in props


@pytest.mark.asyncio
async def test_init_country_centers_has_entries(client):
    resp = await client.get("/init")
    assert resp.status_code == 200
    centers = resp.json()["country_centers"]
    assert isinstance(centers, dict)
    assert len(centers) > 0


@pytest.mark.asyncio
async def test_init_country_center_has_lon_lat_zoom(client):
    resp = await client.get("/init")
    assert resp.status_code == 200
    centers = resp.json()["country_centers"]
    entry = next(iter(centers.values()))
    assert "lon" in entry
    assert "lat" in entry
    assert "zoom" in entry


@pytest.mark.asyncio
async def test_init_lang_pl_returns_polish_names(client):
    resp_en = await client.get("/init", params={"lang": "en"})
    resp_pl = await client.get("/init", params={"lang": "pl"})
    assert resp_en.status_code == 200
    assert resp_pl.status_code == 200
    assert resp_en.json()["geojson"] != resp_pl.json()["geojson"]
