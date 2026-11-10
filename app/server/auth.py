"""Connection token resolution for each MCP call."""

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from app.client.api_client import SmartPotClient, UserAPI
from app.core.config import settings
from app.core.security import bearer_from_headers, is_connection_token

MISSING_TOKEN = (
    "Missing SmartPot connection token. Create one in the application under Profile › Connections and configure it "
    "in your MCP client (Authorization header over HTTP or SMARTPOT_API_TOKEN in stdio)."
)


def connection_token(ctx: Context | None) -> str:
    """Extracts the caller's token from the HTTP request Authorization header or, in stdio, the environment."""
    headers = None
    if ctx is not None:
        try:
            headers = ctx.headers
        except ValueError:
            # Fuera de una petición HTTP (llamadas directas en pruebas o transporte stdio sin contexto HTTP).
            headers = None
    # En transporte HTTP se exige siempre cabecera Authorization: Bearer explícita; en stdio se usa el de entorno.
    token = bearer_from_headers(headers) if headers is not None else settings.api_token
    if not is_connection_token(token):
        raise ToolError(MISSING_TOKEN)
    return token


def user_api(client: SmartPotClient, ctx: Context | None) -> UserAPI:
    return client.for_token(connection_token(ctx))
