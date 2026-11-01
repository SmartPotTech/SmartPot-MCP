"""Instanciación y cableado del servidor MCP de SmartPot."""

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.client.api_client import SmartPotClient
from app.server.prompts import register_prompts
from app.server.resources import register_resources
from app.server.tools import register_tools

VERSION = "1.0.0"


def create_mcp_server(client: SmartPotClient | None = None) -> MCPServer:
    """Crea el servidor con sus herramientas, recursos, prompts y la sonda de salud."""
    api_client = client or SmartPotClient()

    mcp = MCPServer(
        name="SmartPot",
        version=VERSION,
        description="Cultivos hidropónicos de SmartPot: telemetría, diagnóstico de la IA y control de actuadores",
        instructions=(
            "Servidor MCP de SmartPot para monitorear y automatizar cultivos hidropónicos. Cada conexión pertenece "
            "a una cuenta y tiene un alcance: de solo lectura o de control. Antes de accionar un actuador, crear, "
            "editar o borrar un cultivo, pide confirmación explícita a la persona."
        ),
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health_endpoint(request: Request) -> JSONResponse:
        try:
            api_status = (await api_client.health()).get("status", "UNKNOWN")
        except Exception:
            api_status = "DOWN"
        return JSONResponse(
            {"status": "UP" if api_status == "UP" else "DEGRADED", "service": "smartpot-mcp", "api": api_status}
        )

    register_tools(mcp, api_client)
    register_resources(mcp, api_client)
    register_prompts(mcp)
    return mcp
