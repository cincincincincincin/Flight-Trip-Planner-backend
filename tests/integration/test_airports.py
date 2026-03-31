"""
Testy integracyjne dla endpointów lotnisk (/airports).
"""


async def test_geojson_struktura(client):
    resp = await client.get("/airports/geojson")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert "features" in data
    assert len(data["features"]) > 0


async def test_geojson_format_feature(client):
    resp = await client.get("/airports/geojson")
    assert resp.status_code == 200
    feature = resp.json()["features"][0]
    assert feature["type"] == "Feature"
    assert "geometry" in feature
    assert "properties" in feature
    assert feature["geometry"]["type"] == "Point"
    assert len(feature["geometry"]["coordinates"]) == 2


async def test_geojson_properties_zawieraja_kod(client):
    resp = await client.get("/airports/geojson")
    assert resp.status_code == 200
    props = resp.json()["features"][0]["properties"]
    assert "code" in props
    assert "name" in props
    assert "city_code" in props
    assert "country_code" in props


async def test_geojson_zawiera_waw(client):
    resp = await client.get("/airports/geojson")
    assert resp.status_code == 200
    codes = {f["properties"]["code"] for f in resp.json()["features"]}
    assert "WAW" in codes


async def test_geojson_parametr_jezyka(client):
    resp_pl = await client.get("/airports/geojson", params={"lang": "pl"})
    resp_en = await client.get("/airports/geojson", params={"lang": "en"})
    assert resp_pl.status_code == 200
    assert resp_en.status_code == 200
