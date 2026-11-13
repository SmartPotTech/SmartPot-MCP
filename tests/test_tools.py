"""Tools invoked directly (as in stdio mode, using the environment token)."""

import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app.client.api_client import UserAPI
from tests.conftest import ACTUATOR, CROP, READ_ONLY, TOKEN_ANA

NOTIFICATION = "66f5a1000000000000000301"
CROP_2 = "66f5a1000000000000000102"

TOOL_INVENTORY = {
    "get_account",
    "list_crops",
    "get_crop",
    "create_crop",
    "update_crop",
    "delete_crop",
    "set_crop_automation",
    "get_crop_weather",
    "get_latest_reading",
    "get_readings_history",
    "get_readings_summary",
    "record_reading",
    "list_actuators",
    "send_actuator_command",
    "send_bulk_command",
    "list_commands",
    "get_crop_insights",
    "get_crop_profiles",
    "get_learning_status",
    "get_overview",
    "get_metric_series",
    "get_fleet",
    "list_notifications",
    "get_unread_count",
    "mark_notification_read",
}

# (herramienta, argumentos, método HTTP, ruta, params, cuerpo, fragmento de la respuesta)
TOOL_CASES = [
    ("get_account", {}, "GET", "/api/v1/users/me", {}, None, "ana@smartpot.app"),
    ("list_crops", {}, "GET", "/api/v1/crops", {}, None, "Ana's lettuce"),
    ("get_crop", {"crop_id": CROP}, "GET", f"/api/v1/crops/{CROP}", {}, None, "Lettuce"),
    (
        "create_crop",
        {"name": "Basil", "crop_type": "BASIL", "kind": "REAL"},
        "POST",
        "/api/v1/crops",
        {},
        {"name": "Basil", "type": "BASIL", "kind": "REAL"},
        "Credentials issued",
    ),
    (
        "update_crop",
        {"crop_id": CROP, "name": "New lettuce"},
        "PUT",
        f"/api/v1/crops/{CROP}",
        {},
        {"name": "New lettuce", "type": "LETTUCE", "form": "NFT"},
        "Lettuce",
    ),
    ("delete_crop", {"crop_id": CROP}, "DELETE", f"/api/v1/crops/{CROP}", {}, None, "DELETED"),
    (
        "set_crop_automation",
        {"crop_id": CROP, "enabled": True},
        "PUT",
        f"/api/v1/crops/{CROP}/automation",
        {},
        {"enabled": True},
        '"ok"',
    ),
    ("get_crop_weather", {"crop_id": CROP}, "GET", f"/api/v1/crops/{CROP}/weather", {}, None, '"ok"'),
    ("get_latest_reading", {"crop_id": CROP}, "GET", f"/api/v1/crops/{CROP}/readings/latest", {}, None, '"ok"'),
    (
        "get_readings_history",
        {"crop_id": CROP, "from_time": "2026-11-01T00:00:00Z", "to_time": "2026-11-02T00:00:00Z", "limit": 10},
        "GET",
        f"/api/v1/crops/{CROP}/readings",
        {"limit": "10", "from": "2026-11-01T00:00:00Z", "to": "2026-11-02T00:00:00Z"},
        None,
        "21.5",
    ),
    (
        "get_readings_summary",
        {"crop_id": CROP, "hours": 6},
        "GET",
        f"/api/v1/crops/{CROP}/readings/summary",
        {"hours": "6"},
        None,
        '"ok"',
    ),
    (
        "record_reading",
        {"crop_id": CROP, "temperature": 21.5, "soil_moisture": 60.0},
        "POST",
        f"/api/v1/crops/{CROP}/readings",
        {},
        {"temperature": 21.5, "soilMoisture": 60.0},
        '"ok"',
    ),
    ("list_actuators", {"crop_id": CROP}, "GET", f"/api/v1/crops/{CROP}/actuators", {}, None, "FAN"),
    (
        "send_actuator_command",
        {"crop_id": CROP, "actuator_id": ACTUATOR, "action": "ACTIVATE", "duration_seconds": 60},
        "POST",
        f"/api/v1/crops/{CROP}/commands",
        {},
        {"actuatorId": ACTUATOR, "action": "ACTIVATE", "durationSeconds": 60},
        "PENDING",
    ),
    (
        "send_bulk_command",
        {"crop_ids": [CROP, CROP_2], "actuator_type": "FAN", "action": "DEACTIVATE", "duration_seconds": 30},
        "POST",
        "/api/v1/commands/bulk",
        {},
        {"cropIds": [CROP, CROP_2], "actuatorType": "FAN", "action": "DEACTIVATE", "durationSeconds": 30},
        '"ok"',
    ),
    (
        "list_commands",
        {"crop_id": CROP, "limit": 5},
        "GET",
        f"/api/v1/crops/{CROP}/commands",
        {"limit": "5"},
        None,
        "EXECUTED",
    ),
    ("get_crop_insights", {"crop_id": CROP}, "GET", f"/api/v1/crops/{CROP}/insights", {}, None, '"ok"'),
    ("get_crop_profiles", {}, "GET", "/api/v1/crop-profiles", {}, None, "LETTUCE"),
    ("get_learning_status", {}, "GET", "/api/v1/ai/learning", {}, None, '"ok"'),
    ("get_overview", {}, "GET", "/api/v1/overview", {}, None, '"ok"'),
    (
        "get_metric_series",
        {"metric": "ph", "hours": 6},
        "GET",
        "/api/v1/overview/series",
        {"metric": "ph", "hours": "6"},
        None,
        '"ok"',
    ),
    ("get_fleet", {}, "GET", "/api/v1/overview/fleet", {}, None, '"ok"'),
    ("list_notifications", {}, "GET", "/api/v1/notifications", {}, None, '"ok"'),
    ("get_unread_count", {}, "GET", "/api/v1/notifications/unread-count", {}, None, '"ok"'),
    (
        "mark_notification_read",
        {"notification_id": NOTIFICATION},
        "PUT",
        f"/api/v1/notifications/{NOTIFICATION}/read",
        {},
        None,
        '"ok"',
    ),
]


def _text(result) -> str:
    return "".join(getattr(block, "text", "") for block in result.content)


async def test_list_crops_uses_the_connection_token(mcp_server, fake_api, stdio_token):
    result = await mcp_server.call_tool("list_crops", {})
    assert not result.is_error
    assert "Ana's lettuce" in _text(result)
    assert ("GET", "/api/v1/crops", TOKEN_ANA) in fake_api.seen


async def test_without_token_the_tool_explains_how_to_connect(mcp_server, fake_api, stdio_token):
    stdio_token(None)
    with pytest.raises(ToolError, match="Profile › Connections"):
        await mcp_server.call_tool("list_crops", {})
    assert fake_api.seen == []


async def test_a_session_jwt_is_not_accepted_as_connection(mcp_server, fake_api, stdio_token):
    stdio_token("eyJhbGciOiJIUzI1NiJ9.payload.signature")
    with pytest.raises(ToolError):
        await mcp_server.call_tool("list_crops", {})
    assert fake_api.seen == []


async def test_read_only_connection_cannot_move_actuators(mcp_server, stdio_token):
    stdio_token(READ_ONLY)
    with pytest.raises(Exception, match="read-only"):
        await mcp_server.call_tool(
            "send_actuator_command", {"crop_id": CROP, "actuator_id": ACTUATOR, "action": "ACTIVATE"}
        )


async def test_invalid_identifier_never_reaches_the_api(mcp_server, fake_api, stdio_token):
    with pytest.raises(ToolError):
        await mcp_server.call_tool("get_crop", {"crop_id": "../../users/me"})
    assert fake_api.seen == []


async def test_create_crop_hides_device_credentials(mcp_server, stdio_token):
    result = await mcp_server.call_tool("create_crop", {"name": "Basil", "crop_type": "BASIL", "kind": "REAL"})
    assert not result.is_error
    assert "secret" not in _text(result)


async def test_account_tool_names_the_connected_account(mcp_server, stdio_token):
    result = await mcp_server.call_tool("get_account", {})
    assert json.loads(_text(result))["email"] == "ana@smartpot.app"


async def test_profiles_are_public(mcp_server, fake_api, stdio_token):
    stdio_token(None)
    result = await mcp_server.call_tool("get_crop_profiles", {})
    assert not result.is_error
    assert ("GET", "/api/v1/crop-profiles", None) in fake_api.seen


async def test_every_registered_tool_is_inventoried_with_its_schema(mcp_server):
    tools = {tool.name: tool for tool in await mcp_server.list_tools()}
    assert set(tools) == TOOL_INVENTORY
    assert tools["get_account"].annotations.read_only_hint is True
    assert tools["get_crop"].input_schema["required"] == ["crop_id"]
    assert set(tools["create_crop"].input_schema["required"]) == {"name", "crop_type"}
    assert tools["delete_crop"].annotations.destructive_hint is True
    assert tools["send_actuator_command"].annotations.read_only_hint is False
    assert tools["set_crop_automation"].annotations.idempotent_hint is True


@pytest.mark.parametrize(
    "name,arguments,method,path,params,body,expected",
    TOOL_CASES,
    ids=[case[0] for case in TOOL_CASES],
)
async def test_each_tool_calls_the_expected_api_route(
    mcp_server, fake_api, stdio_token, name, arguments, method, path, params, body, expected
):
    result = await mcp_server.call_tool(name, arguments)
    assert not result.is_error, _text(result)
    assert expected in _text(result)
    call = fake_api.details[-1]
    assert (call["method"], call["path"]) == (method, path)
    assert call["params"] == params
    if body is not None:
        assert call["body"] == body
    # `get_crop_profiles` es público; el resto usa siempre el token de la conexión.
    expected_token = None if name == "get_crop_profiles" else TOKEN_ANA
    assert call["token"] == expected_token


async def test_update_crop_reads_the_current_values_before_writing(mcp_server, fake_api, stdio_token):
    result = await mcp_server.call_tool("update_crop", {"crop_id": CROP, "name": "New lettuce"})
    assert not result.is_error
    first, second = fake_api.details[-2:]
    assert (first["method"], first["path"]) == ("GET", f"/api/v1/crops/{CROP}")
    assert (second["method"], second["path"]) == ("PUT", f"/api/v1/crops/{CROP}")


async def test_update_crop_merges_existing_placement_and_validates_coordinates(
    mcp_server, fake_api, monkeypatch, stdio_token
):
    existing = {
        "id": CROP,
        "name": "Lettuce",
        "type": "LETTUCE",
        "form": "NFT",
        "placement": {
            "setting": "OUTDOOR",
            "exposure": "FULL_SUN",
            "location": {"name": "Medellin", "latitude": 6.24, "longitude": -75.57},
        },
    }

    async def mock_get_crop(self, crop_id):
        return existing

    monkeypatch.setattr(UserAPI, "get_crop", mock_get_crop)
    result = await mcp_server.call_tool("update_crop", {"crop_id": CROP, "place_name": "Rooftop"})
    assert not result.is_error
    assert fake_api.details[-1]["body"]["placement"] == {
        "setting": "OUTDOOR",
        "exposure": "FULL_SUN",
        "location": {"name": "Rooftop", "latitude": 6.24, "longitude": -75.57},
    }


async def test_create_crop_placement_requires_both_coordinates_and_supplies_nonempty_place_name(
    mcp_server, fake_api, stdio_token
):
    with pytest.raises(ToolError, match="latitude and longitude"):
        await mcp_server.call_tool("create_crop", {"name": "Basil", "crop_type": "BASIL", "latitude": 4.65})
    assert fake_api.seen == []

    result = await mcp_server.call_tool(
        "create_crop",
        {"name": "Basil", "crop_type": "BASIL", "latitude": 4.65, "longitude": -74.05},
    )
    assert not result.is_error
    assert fake_api.details[-1]["body"]["placement"] == {
        "location": {"name": "4.6500, -74.0500", "latitude": 4.65, "longitude": -74.05}
    }


async def test_create_virtual_crop_builds_placement_and_simulation(mcp_server, fake_api, stdio_token):
    arguments = {
        "name": "Balcony basil",
        "crop_type": "BASIL",
        "setting": "OUTDOOR",
        "exposure": "PARTIAL_SUN",
        "place_name": "Balcony",
        "latitude": 4.65,
        "longitude": -74.05,
        "virtual_mode": "MANUAL",
        "virtual_interval_seconds": 30,
    }
    result = await mcp_server.call_tool("create_crop", arguments)
    assert not result.is_error
    body = fake_api.details[-1]["body"]
    assert body["kind"] == "VIRTUAL"
    assert body["placement"] == {
        "setting": "OUTDOOR",
        "exposure": "PARTIAL_SUN",
        "location": {"name": "Balcony", "latitude": 4.65, "longitude": -74.05},
    }
    assert body["virtual"] == {"mode": "MANUAL", "intervalSeconds": 30}


async def test_record_reading_needs_at_least_one_measure(mcp_server, fake_api, stdio_token):
    with pytest.raises(ToolError, match="at least one measured variable"):
        await mcp_server.call_tool("record_reading", {"crop_id": CROP})
    assert fake_api.seen == []


async def test_record_reading_rejects_real_crops(mcp_server, monkeypatch, stdio_token):
    # Un cultivo real rechaza la inyección de lecturas manuales por API o MCP.
    async def mock_get_crop(self, crop_id):
        return {"id": crop_id, "name": "Real Lettuce", "kind": "REAL"}

    monkeypatch.setattr(UserAPI, "get_crop", mock_get_crop)
    with pytest.raises(ToolError, match="Manual readings are only allowed for virtual crops"):
        await mcp_server.call_tool("record_reading", {"crop_id": CROP, "temperature": 22.0})


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("delete_crop", {"crop_id": CROP}),
        ("set_crop_automation", {"crop_id": CROP, "enabled": True}),
        ("record_reading", {"crop_id": CROP, "temperature": 21.0}),
        ("send_actuator_command", {"crop_id": CROP, "actuator_id": ACTUATOR, "action": "ACTIVATE"}),
        (
            "send_bulk_command",
            {"crop_ids": [CROP], "actuator_type": "FAN", "action": "DEACTIVATE"},
        ),
        ("mark_notification_read", {"notification_id": NOTIFICATION}),
        ("create_crop", {"name": "Basil", "crop_type": "BASIL"}),
        ("update_crop", {"crop_id": CROP, "name": "Renamed"}),
    ],
)
async def test_read_only_connection_blocks_every_write(mcp_server, fake_api, stdio_token, name, arguments):
    stdio_token(READ_ONLY)
    with pytest.raises(Exception, match="read-only"):
        await mcp_server.call_tool(name, arguments)
    # El guard de SmartPot-API rechaza la mutación: no se ejecuta ningún cambio de estado.
    call = fake_api.details[-1]
    assert call["method"] != "GET"
    assert call["token"] == READ_ONLY


@pytest.mark.parametrize(
    "name,arguments,field",
    [
        ("get_crop", {"crop_id": "../../users/me"}, "crop_id"),
        ("delete_crop", {"crop_id": "not-an-object-id"}, "crop_id"),
        ("get_latest_reading", {"crop_id": CROP.upper() + "0"}, "crop_id"),
        (
            "send_actuator_command",
            {"crop_id": CROP, "actuator_id": "../../crops", "action": "ACTIVATE"},
            "actuator_id",
        ),
        (
            "send_bulk_command",
            {"crop_ids": [CROP, "../me"], "actuator_type": "FAN", "action": "ACTIVATE"},
            "crop_ids",
        ),
        ("mark_notification_read", {"notification_id": "66f5a1"}, "notification_id"),
    ],
)
async def test_invalid_identifiers_never_reach_the_api(mcp_server, fake_api, stdio_token, name, arguments, field):
    with pytest.raises(ToolError, match=field):
        await mcp_server.call_tool(name, arguments)
    assert fake_api.seen == []


async def test_resources_expose_crop_state_as_json(mcp_server, fake_api, stdio_token):
    resources = {resource.name for resource in await mcp_server.list_resources()}
    assert resources == {"crop_profiles", "health"}

    crop = await mcp_server.read_resource(f"smartpot://crops/{CROP}")
    assert json.loads(crop[0].content)["id"] == CROP
    assert crop[0].mime_type == "application/json"

    latest = await mcp_server.read_resource(f"smartpot://crops/{CROP}/latest")
    assert json.loads(latest[0].content) == {"ok": True}
    insights = await mcp_server.read_resource(f"smartpot://crops/{CROP}/insights")
    assert json.loads(insights[0].content) == {"ok": True}
    assert [path for _, path, _ in fake_api.seen].count(f"/api/v1/crops/{CROP}") == 1


async def test_public_resources_do_not_send_a_token(mcp_server, fake_api, stdio_token):
    stdio_token(None)
    profiles = await mcp_server.read_resource("smartpot://profiles")
    health = await mcp_server.read_resource("smartpot://health")
    assert json.loads(profiles[0].content)[0]["type"] == "LETTUCE"
    assert json.loads(health[0].content)["status"] == "UP"
    tokens = [token for _, path, token in fake_api.seen if path in ("/api/v1/crop-profiles", "/health")]
    assert tokens == [None, None]


async def test_prompts_describe_the_available_workflows(mcp_server):
    prompts = {prompt.name: prompt for prompt in await mcp_server.list_prompts()}
    assert set(prompts) == {"agronomic_diagnosis", "emergency_triage", "fleet_daily_summary"}
    assert [argument.name for argument in prompts["emergency_triage"].arguments] == ["crop_id", "alert"]

    diagnosis = await mcp_server.get_prompt("agronomic_diagnosis", {"crop_id": CROP, "goal": "flowering"})
    text = diagnosis.messages[0].content.text
    assert CROP in text and "flowering" in text and "get_crop_insights" in text

    triage = await mcp_server.get_prompt("emergency_triage", {"crop_id": CROP, "alert": "dry substrate"})
    text = triage.messages[0].content.text
    assert "dry substrate" in text and "send_actuator_command" in text

    summary = await mcp_server.get_prompt("fleet_daily_summary", {"hours": 12})
    text = summary.messages[0].content.text
    assert "last 12 h" in text and "get_overview" in text


async def test_tool_validation_aligns_with_api_limits(mcp_server, fake_api, stdio_token):
    with pytest.raises(ToolError, match="WEATHER"):
        await mcp_server.call_tool(
            "create_crop",
            {"name": "WeatherBasil", "crop_type": "BASIL", "kind": "VIRTUAL", "virtual_mode": "WEATHER"},
        )
    with pytest.raises(ToolError, match="virtual_interval_seconds"):
        await mcp_server.call_tool(
            "create_crop",
            {"name": "FastBasil", "crop_type": "BASIL", "kind": "VIRTUAL", "virtual_interval_seconds": 5},
        )
    with pytest.raises(ToolError, match="temperature"):
        await mcp_server.call_tool("record_reading", {"crop_id": CROP, "temperature": 61.0})
    with pytest.raises(ToolError, match="atmosphere"):
        await mcp_server.call_tool("record_reading", {"crop_id": CROP, "atmosphere": 100.0})
    with pytest.raises(ToolError, match="tds"):
        await mcp_server.call_tool("record_reading", {"crop_id": CROP, "tds": 10001.0})
    with pytest.raises(ToolError, match="crop_ids"):
        await mcp_server.call_tool(
            "send_bulk_command",
            {"crop_ids": [CROP] * 21, "actuator_type": "FAN", "action": "ACTIVATE"},
        )
    assert fake_api.seen == []


async def test_account_and_validation_error_details_surface_api_fields(mcp_server, monkeypatch, stdio_token):
    import httpx

    from app.client.api_client import SmartPotClient, _error_message

    resp = httpx.Response(
        400,
        json={"message": "Validation failed", "fields": {"latitude": "Required for weather mode"}},
    )
    msg = _error_message(resp)
    assert "Validation failed" in msg and "latitude: Required for weather mode" in msg

    async def rich_me(self):
        return {"id": "u1", "name": "Ana", "lastName": "Perez", "email": "ana@smartpot.app", "role": "USER"}

    monkeypatch.setattr(UserAPI, "me", rich_me)
    result = await mcp_server.call_tool("get_account", {})
    data = json.loads(_text(result))
    assert data["role"] == "USER"
    assert isinstance(SmartPotClient(base_url="http://api.test"), SmartPotClient)
