"""SmartPot MCP server instantiation and wiring."""

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.client.api_client import SmartPotClient
from app.server.prompts import register_prompts
from app.server.resources import register_resources
from app.server.tools import register_tools

VERSION = "1.0.0"


def create_mcp_server(client: SmartPotClient | None = None) -> MCPServer:
    """Creates the server with its tools, resources, prompts, and health probe."""
    api_client = client or SmartPotClient()

    mcp = MCPServer(
        name="SmartPot",
        version=VERSION,
        description="SmartPot hydroponic crops: telemetry, AI diagnosis, and actuator control",
        instructions=(
            "SmartPot MCP server for monitoring and automating hydroponic crops. Each connection belongs "
            "to an account and has a scope: read-only or control. Before triggering an actuator or creating, "
            "editing, or deleting a crop, ask the user for explicit confirmation."
        ),
    )

    @mcp.custom_route("/livez", methods=["GET"])
    async def liveness_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"status": "UP", "service": "smartpot-mcp"})

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
    # El middleware HTTP reutiliza el mismo pool para validar los tokens de conexión.
    mcp.smartpot_client = api_client
    return mcp
