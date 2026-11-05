"""Entrypoint: stdio for local clients or streamable HTTP for the container."""

import sys

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.logging import logger
from app.core.security import ConnectionTokenMiddleware
from app.server.mcp_server import create_mcp_server

mcp = create_mcp_server()


def build_http_app(server: MCPServer | None = None) -> ASGIApp:
    """Stateless HTTP app: each request carries the caller's connection token and is served in isolation."""
    app = (server or mcp).streamable_http_app(
        streamable_http_path=settings.mcp_path,
        stateless_http=True,
        json_response=True,
        host=settings.host,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.split(settings.allowed_hosts),
            allowed_origins=settings.split(settings.allowed_origins),
        ),
    )
    app = ConnectionTokenMiddleware(app)
    return CORSMiddleware(
        app,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
    )


# Aplicación ASGI para uvicorn (contenedor).
app = build_http_app()


def main() -> None:
    transport = settings.transport
    logger.info("Starting SmartPot MCP in '%s' mode", transport)
    if transport == "stdio":
        mcp.run("stdio")
    elif transport == "streamable-http":
        uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower())
    else:
        logger.error("Unknown transport mode: %s", transport)
        sys.exit(1)


if __name__ == "__main__":
    main()
