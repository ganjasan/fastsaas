"""Smoke tests for the bootstrap-only `/health` endpoint."""

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    """GIVEN a freshly-started app, WHEN GET /health, THEN it returns status=ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
