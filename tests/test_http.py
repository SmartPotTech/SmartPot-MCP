"""HTTP transport: each request uses the caller's token and nothing is shared across accounts."""

import json

import httpx
import pytest
from starlette.testclient import TestClient

from app.client.api_client import SmartPotClient
from app.core.config import settings
from app.main import build_http_app
from app.server.mcp_server import create_mcp_server
from tests.conftest import ACCOUNTS, CROP, TOKEN_ANA, TOKEN_LUIS

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def http(mcp_server):
    with TestClient(build_http_app(mcp_server), base_url="http://localhost:8002") as client:
        yield client


def _call(http: TestClient, token: str | None, tool: str, arguments: dict | None = None, host: str | None = None):
    headers = dict(HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if host:
        headers["Host"] = host
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments or {}}}
    return http.post("/mcp", headers=headers, content=json.dumps(body))


def _list(http: TestClient, token: str | None, host: str | None = None):
    return _rpc(http, token, "tools/list", host=host)


def _rpc(
    http: TestClient,
    token: str | None,
    method: str,
    params: dict | None = None,
    host: str | None = None,
):
    headers = dict(HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if host:
        headers["Host"] = host
    body: dict = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
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


def test_fabricated_well_formed_token_is_rejected_on_tools_list(http, fake_api):
    fabricated = "spt_" + "z" * 43
    resp = _list(http, fabricated)
    assert resp.status_code == 401
    assert "invalid or has been revoked" in resp.json()["error"]
    assert any(path == "/api/v1/users/me" and token == fabricated for _, path, token in fake_api.seen)


def test_token_validation_is_cached_for_the_short_ttl(http, fake_api):
    first = _list(http, TOKEN_ANA)
    second = _list(http, TOKEN_ANA)
    assert first.status_code == second.status_code == 200
    validations = [entry for entry in fake_api.seen if entry[1] == "/api/v1/users/me"]
    assert len(validations) == 1


def test_token_cache_can_be_disabled(fake_api, monkeypatch):
    monkeypatch.setattr(settings, "token_cache_seconds", 0.0)
    client = SmartPotClient(base_url="http://api.test", transport=httpx.MockTransport(fake_api))
    with TestClient(build_http_app(create_mcp_server(client)), base_url="http://localhost:8002") as http:
        assert _list(http, TOKEN_ANA).status_code == 200
        assert _list(http, TOKEN_ANA).status_code == 200
    validations = [entry for entry in fake_api.seen if entry[1] == "/api/v1/users/me"]
    assert len(validations) == 2


def test_unknown_host_is_rejected(http):
    resp = http.post(
        "/mcp", headers={**HEADERS, "Authorization": f"Bearer {TOKEN_ANA}", "Host": "attacker.example"}, content="{}"
    )
    assert resp.status_code in (400, 403, 421)


def test_host_parser_accepts_only_exact_authorities(http):
    assert _list(http, TOKEN_ANA, host="localhost:28092").status_code == 200
    assert _list(http, TOKEN_ANA, host="LOCALHOST:28092").status_code == 200
    assert _list(http, TOKEN_ANA, host="[::1]:28092").status_code == 200
    assert _list(http, TOKEN_ANA, host="localhost").status_code == 200
    for host in ("localhost:99999", "localhost:28092.evil.example", "localhost:28092x", "localhost:"):
        assert _list(http, TOKEN_ANA, host=host).status_code in (400, 403, 421), host


def test_cors_preflight_options(http):
    resp = http.options(
        "/mcp",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert resp.headers.get("access-control-allow-origin") != "*"


def test_cors_rejects_an_unlisted_origin(http):
    resp = http.options(
        "/mcp",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 400
    assert "access-control-allow-origin" not in resp.headers


def test_an_actual_post_with_an_unlisted_origin_is_forbidden(http):
    resp = http.post(
        "/mcp",
        headers={
            **HEADERS,
            "Authorization": f"Bearer {TOKEN_ANA}",
            "Origin": "https://evil.example",
        },
        content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "Origin is not allowed"


def test_tools_resources_and_prompts_over_http(http, fake_api):
    tools = _list(http, TOKEN_ANA)
    assert tools.status_code == 200
    names = {tool["name"] for tool in tools.json()["result"]["tools"]}
    assert "send_actuator_command" in names and len(names) == 25

    templates = _rpc(http, TOKEN_ANA, "resources/templates/list")
    assert templates.status_code == 200
    uris = {item["uriTemplate"] for item in templates.json()["result"]["resourceTemplates"]}
    assert uris == {
        "smartpot://crops/{crop_id}",
        "smartpot://crops/{crop_id}/latest",
        "smartpot://crops/{crop_id}/insights",
    }

    resource = _rpc(http, TOKEN_ANA, "resources/read", {"uri": f"smartpot://crops/{CROP}"})
    assert resource.status_code == 200
    contents = resource.json()["result"]["contents"]
    assert contents[0]["mimeType"] == "application/json"
    assert json.loads(contents[0]["text"])["id"] == CROP

    prompts = _rpc(http, TOKEN_ANA, "prompts/list")
    prompt_names = {prompt["name"] for prompt in prompts.json()["result"]["prompts"]}
    assert prompt_names == {"agronomic_diagnosis", "emergency_triage", "fleet_daily_summary"}
    prompt = _rpc(
        http,
        TOKEN_ANA,
        "prompts/get",
        {"name": "agronomic_diagnosis", "arguments": {"crop_id": CROP, "goal": "stable growth"}},
    )
    text = prompt.json()["result"]["messages"][0]["content"]["text"]
    assert CROP in text and "stable growth" in text
    assert any(path == f"/api/v1/crops/{CROP}" for _, path, _ in fake_api.seen)


def test_revoked_token_invalidates_the_cache(http, fake_api, monkeypatch):
    assert _list(http, TOKEN_ANA).status_code == 200
    monkeypatch.delitem(ACCOUNTS, TOKEN_ANA)

    # La herramienta ya no puede usarse: la API responde 401 y el servidor MCP lo propaga.
    denied = _call(http, TOKEN_ANA, "list_crops")
    assert denied.status_code == 200
    assert "invalid or has been revoked" in denied.text

    # La siguiente petición HTTP no puede seguir aceptando el veredicto cacheado.
    assert _list(http, TOKEN_ANA).status_code == 401
    validations = [entry for entry in fake_api.seen if entry[1] == "/api/v1/users/me" and entry[2] == TOKEN_ANA]
    assert len(validations) >= 2


def test_token_validation_outage_returns_503_and_is_not_cached():
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("API down", request=request)

    client = SmartPotClient(base_url="http://api.test", transport=httpx.MockTransport(unavailable))
    with TestClient(build_http_app(create_mcp_server(client)), base_url="http://localhost:8002") as http:
        first = _list(http, TOKEN_ANA)
        second = _list(http, TOKEN_ANA)
    assert first.status_code == second.status_code == 503
    assert "could not be validated" in first.json()["error"]


def test_invalid_identifiers_do_not_change_the_api_path(http, fake_api):
    for tool, arguments, field in [
        ("get_crop", {"crop_id": "../../users/me"}, "crop_id"),
        (
            "send_actuator_command",
            {"crop_id": CROP, "actuator_id": "../commands", "action": "ACTIVATE"},
            "actuator_id",
        ),
        ("mark_notification_read", {"notification_id": "not-an-id"}, "notification_id"),
    ]:
        resp = _call(http, TOKEN_ANA, tool, arguments)
        assert resp.status_code == 200
        assert field in resp.text
        assert all(".." not in path for _, path, _ in fake_api.seen)
