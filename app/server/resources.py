"""SmartPot MCP resources (`@mcp.resource()`): read-only JSON context.

Account-scoped resources include the crop ID in the URI (the SDK only provides the request context, and with it
the token, to URI templates); the crop list and general overview are exposed as tools."""

import json
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from app.client.api_client import SmartPotClient
from app.server.auth import user_api


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def register_resources(mcp: MCPServer, client: SmartPotClient) -> None:
    @mcp.resource("smartpot://crops/{crop_id}", name="crop", mime_type="application/json")
    async def crop(ctx: Context, crop_id: str) -> str:
        """Crop details."""
        return _json(await user_api(client, ctx).get_crop(crop_id))

    @mcp.resource("smartpot://crops/{crop_id}/latest", name="crop_latest_reading", mime_type="application/json")
    async def crop_latest(ctx: Context, crop_id: str) -> str:
        """Latest reading for a crop."""
        return _json(await user_api(client, ctx).latest_reading(crop_id))

    @mcp.resource("smartpot://crops/{crop_id}/insights", name="crop_insights", mime_type="application/json")
    async def crop_insights(ctx: Context, crop_id: str) -> str:
        """AI diagnosis for a crop."""
        return _json(await user_api(client, ctx).insights(crop_id))

    @mcp.resource("smartpot://profiles", name="crop_profiles", mime_type="application/json")
    async def profiles() -> str:
        """Optimal ranges by crop species (public)."""
        return _json(await client.crop_profiles())

    @mcp.resource("smartpot://health", name="health", mime_type="application/json")
    async def health() -> str:
        """Status of the API and its dependencies (database, cache, broker, AI, simulator); public."""
        return _json(await client.health())
