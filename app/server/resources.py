"""Recursos MCP de SmartPot (`@mcp.resource()`): contexto de solo lectura en JSON.

Los recursos de una cuenta llevan el cultivo en la URI (el SDK solo da el contexto de la petición, y con él el
token, a las plantillas); la lista de cultivos y el panel general están como herramientas."""

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
        """Detalle de un cultivo."""
        return _json(await user_api(client, ctx).get_crop(crop_id))

    @mcp.resource("smartpot://crops/{crop_id}/latest", name="crop_latest_reading", mime_type="application/json")
    async def crop_latest(ctx: Context, crop_id: str) -> str:
        """Última lectura de un cultivo."""
        return _json(await user_api(client, ctx).latest_reading(crop_id))

    @mcp.resource("smartpot://crops/{crop_id}/insights", name="crop_insights", mime_type="application/json")
    async def crop_insights(ctx: Context, crop_id: str) -> str:
        """Diagnóstico de la IA para un cultivo."""
        return _json(await user_api(client, ctx).insights(crop_id))

    @mcp.resource("smartpot://profiles", name="crop_profiles", mime_type="application/json")
    async def profiles() -> str:
        """Rangos óptimos por tipo de cultivo (público)."""
        return _json(await client.crop_profiles())

    @mcp.resource("smartpot://health", name="health", mime_type="application/json")
    async def health() -> str:
        """Estado de la API y sus dependencias (base, caché, broker, IA, simulador); público."""
        return _json(await client.health())
