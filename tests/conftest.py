"""Fixtures: simulated SmartPot-API recording which token accompanies each request."""

import json
from typing import Any

import httpx
import pytest

from app.client.api_client import SmartPotClient
from app.core.config import settings
from app.server.mcp_server import create_mcp_server

CROP = "66f5a1000000000000000101"
ACTUATOR = "66f5a1000000000000000201"
TOKEN_ANA = "spt_" + "a" * 43
TOKEN_LUIS = "spt_" + "b" * 43
READ_ONLY = "spt_" + "r" * 43

ACCOUNTS = {
    TOKEN_ANA: {"id": "u1", "name": "Ana", "email": "ana@smartpot.app"},
    TOKEN_LUIS: {"id": "u2", "name": "Luis", "email": "luis@smartpot.app"},
    READ_ONLY: {"id": "u1", "name": "Ana", "email": "ana@smartpot.app"},
}


class FakeAPI:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str, str | None]] = []
        # Detalle completo (query y cuerpo) para comprobar el contrato HTTP de cada herramienta.
        self.details: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization")
        token = auth.removeprefix("Bearer ") if auth else None
        path, method = request.url.path, request.method
        self.seen.append((method, path, token))
        raw = request.content
        self.details.append(
            {
                "method": method,
                "path": path,
                "token": token,
                "params": dict(request.url.params),
                "body": json.loads(raw) if raw else None,
            }
        )

        if path == "/health":
            return httpx.Response(200, json={"status": "UP"})
        if path == "/api/v1/crop-profiles":
            return httpx.Response(200, json=[{"type": "LETTUCE", "temperature": {"min": 15, "max": 22}}])
        account = ACCOUNTS.get(token or "")
        if account is None:
            return httpx.Response(401, json={"message": "The connection token is invalid or has been revoked"})
        if method != "GET" and token == READ_ONLY:
            return httpx.Response(403, json={"message": "This connection is read-only"})
        if path == "/api/v1/users/me":
            return httpx.Response(200, json=account)
        if path == "/api/v1/crops" and method == "GET":
            return httpx.Response(200, json=[{"id": CROP, "name": f"{account['name']}'s lettuce"}])
        if path == "/api/v1/crops" and method == "POST":
            return httpx.Response(201, json={"crop": {"id": CROP}, "device": {"key": "secret"}})
        if path == f"/api/v1/crops/{CROP}":
            return httpx.Response(200, json={"id": CROP, "name": "Lettuce", "type": "LETTUCE", "form": "NFT"})
        if path == f"/api/v1/crops/{CROP}/commands" and method == "POST":
            return httpx.Response(202, json={"id": "c1", "status": "PENDING"})
        if path == f"/api/v1/crops/{CROP}/commands" and method == "GET":
            return httpx.Response(200, json=[{"id": "c1", "status": "EXECUTED"}])
        if path == f"/api/v1/crops/{CROP}/actuators":
            return httpx.Response(200, json=[{"id": ACTUATOR, "type": "FAN", "active": False}])
        if path == f"/api/v1/crops/{CROP}/readings" and method == "GET":
            return httpx.Response(200, json=[{"temperature": 21.5, "soilMoisture": 60.0}])
        return httpx.Response(200, json={"ok": True})


@pytest.fixture
def fake_api() -> FakeAPI:
    return FakeAPI()


@pytest.fixture
def client(fake_api: FakeAPI) -> SmartPotClient:
    return SmartPotClient(base_url="http://api.test", transport=httpx.MockTransport(fake_api))


@pytest.fixture
def mcp_server(client: SmartPotClient):
    return create_mcp_server(client)


@pytest.fixture
def stdio_token(monkeypatch: pytest.MonkeyPatch):
    """Simulates stdio: the user's token is provided via environment settings."""

    def set_token(token: str | None) -> None:
        monkeypatch.setattr(settings, "api_token", token)

    set_token(TOKEN_ANA)
    return set_token
