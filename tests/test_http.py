"""HTTP transport: each request uses the caller's token and nothing is shared across accounts."""

import json

import pytest
from starlette.testclient import TestClient

from app.main import build_http_app
from tests.conftest import TOKEN_ANA, TOKEN_LUIS

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def http(mcp_server):
    with TestClient(build_http_app(mcp_server), base_url="http://localhost:8002") as client:
        yield client


def _call(http: TestClient, token: str | None, tool: str, arguments: dict | None = None):
    headers = dict(HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments or {}}}
    return http.post("/mcp", headers=headers, content=json.dumps(body))


def test_health_is_public(http):
    resp = http.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "smartpot-mcp"


def test_mcp_requires_a_connection_token(http, fake_api):
    for token in (None, "eyJhbGciOiJIUzI1NiJ9.payload.signature", "spt_short"):
        resp = _call(http, token, "list_crops")
        assert resp.status_code == 401
        assert "Profile › Connections" in resp.json()["error"]
    assert fake_api.seen == []


def test_each_request_uses_its_own_account(http, fake_api):
    ana = _call(http, TOKEN_ANA, "list_crops")
    luis = _call(http, TOKEN_LUIS, "list_crops")
    assert ana.status_code == luis.status_code == 200
    assert "Ana's lettuce" in ana.text and "Luis" not in ana.text
    assert "Luis's lettuce" in luis.text and "Ana" not in luis.text
    tokens = [token for method, path, token in fake_api.seen if path == "/api/v1/crops"]
    assert tokens == [TOKEN_ANA, TOKEN_LUIS]


def test_unknown_host_is_rejected(http):
    resp = http.post(
        "/mcp", headers={**HEADERS, "Authorization": f"Bearer {TOKEN_ANA}", "Host": "attacker.example"}, content="{}"
    )
    assert resp.status_code in (400, 403, 421)
