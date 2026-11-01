"""Resolución del token de conexión de cada llamada MCP."""

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from app.client.api_client import SmartPotClient, UserAPI
from app.core.config import settings
from app.core.security import bearer_from_headers, is_connection_token

MISSING_TOKEN = (
    "Falta el token de conexión de SmartPot. Créalo en la aplicación, en Perfil › Conexiones, y configúralo en el "
    "cliente MCP (cabecera Authorization en HTTP o SMARTPOT_API_TOKEN en stdio)."
)


def connection_token(ctx: Context | None) -> str:
    """Token de quien llama: la cabecera Authorization de la petición HTTP o, en stdio, el del entorno."""
    headers = None
    if ctx is not None:
        try:
            headers = ctx.headers
        except ValueError:
            # Fuera de una petición (llamadas directas en pruebas o stdio sin cabeceras).
            headers = None
    token = bearer_from_headers(headers) or settings.api_token
    if not is_connection_token(token):
        raise ToolError(MISSING_TOKEN)
    return token


def user_api(client: SmartPotClient, ctx: Context | None) -> UserAPI:
    return client.for_token(connection_token(ctx))
