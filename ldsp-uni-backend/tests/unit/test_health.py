"""Basic health check tests."""


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "status" in data["data"]
    assert "databases" in data["data"]


async def test_version(client):
    resp = await client.get("/api/version")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "ldsp-uni-backend"


async def test_info(client):
    resp = await client.get("/api/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
