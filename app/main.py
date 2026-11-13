"""Entrypoint: stdio for local clients or streamable HTTP for the container."""

import sys

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from app.client.api_client import SmartPotClient
from app.core.config import origin_regex, settings, static_origins
from app.core.logging import logger
from app.core.security import (
    AuthorityValidationMiddleware,
    ConnectionTokenMiddleware,
    TokenValidator,
)
from app.server.mcp_server import create_mcp_server

mcp = create_mcp_server()


def build_http_app(server: MCPServer | None = None, client: SmartPotClient | None = None) -> ASGIApp:
    """Stateless HTTP app: each request carries the caller's connection token and is served in isolation."""
    target = server or mcp
    api_client = client or getattr(target, "smartpot_client", None)
    app = target.streamable_http_app(
        streamable_http_path=settings.mcp_path,
        stateless_http=True,
        json_response=True,
        host=settings.host,
        # La validación estricta de Host/Origin la hace AuthorityValidationMiddleware; el SDK 2.3
        # compara prefijos y aceptaría hosts como `localhost:99999`.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    validator = TokenValidator(api_client, settings.token_cache_seconds)
    if isinstance(api_client, SmartPotClient):
        api_client.on_unauthorized = validator.invalidate
    app = ConnectionTokenMiddleware(app, validator)
    app = AuthorityValidationMiddleware(
        app,
        settings.split(settings.allowed_hosts),
        settings.split(settings.allowed_origins),
    )
    origins = static_origins(settings.split(settings.allowed_origins))
    return CORSMiddleware(
        app,
        allow_origins=origins,
        allow_origin_regex=origin_regex(settings.split(settings.allowed_origins)),
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "Mcp-Session-Id",
            "MCP-Protocol-Version",
            "Last-Event-ID",
        ],
        expose_headers=["Mcp-Session-Id", "MCP-Protocol-Version"],
        allow_credentials=False,
    )


# Aplicación ASGI para uvicorn (contenedor).
app = build_http_app()


def main() -> None:
    transport = settings.transport
    logger.info("Starting SmartPot MCP in '%s' mode", transport)
    if transport == "stdio":
        mcp.run("stdio")
    elif transport == "streamable-http":
        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
            timeout_keep_alive=75,
        )
    else:
        logger.error("Unknown transport mode: %s", transport)
        sys.exit(1)


if __name__ == "__main__":
    main()
