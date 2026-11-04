"""Tools invoked directly (as in stdio mode, using the environment token)."""

import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from tests.conftest import ACTUATOR, CROP, READ_ONLY, TOKEN_ANA


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
