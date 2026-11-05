"""Security controls: object identifiers and connection token validation at the HTTP edge."""

import re
from collections.abc import Mapping

from starlette.types import ASGIApp, Receive, Scope, Send

# Los identificadores de SmartPot son ObjectId de 24 caracteres hexadecimales. Validarlos impide que un
# argumento manipulado (p. ej. "../../users/me") cambie la ruta de la API a la que llama el servidor.
_OBJECT_ID = re.compile(r"^[0-9a-fA-F]{24}$")

# Los tokens de conexión que emite SmartPot-API empiezan así; un JWT de sesión no sirve para conectarse.
CONNECTION_TOKEN_PREFIX = "spt_"
_CONNECTION_TOKEN = re.compile(r"^spt_[A-Za-z0-9_-]{20,128}$")

PUBLIC_PATHS = frozenset({"/health"})


class InvalidIdentifierError(ValueError):
    """Identifier with invalid format."""


def require_object_id(value: str, field: str = "id") -> str:
    if not isinstance(value, str) or not _OBJECT_ID.fullmatch(value):
        raise InvalidIdentifierError(f"Field '{field}' must be a 24-character hexadecimal identifier")
    return value.lower()


def is_connection_token(token: str | None) -> bool:
    return bool(token) and _CONNECTION_TOKEN.fullmatch(token) is not None


def bearer_from_headers(headers: Mapping[str, str] | None) -> str | None:
    """Extracts the token from `Authorization: Bearer …` (Starlette headers are case-insensitive)."""
    if not headers:
        return None
    value = headers.get("authorization") or headers.get("Authorization")
    if not value or not value.startswith("Bearer "):
        return None
    return value[len("Bearer ") :].strip() or None


class ConnectionTokenMiddleware:
    """Requires a SmartPot connection token on all HTTP routes except public endpoints.

    Checks format early to return 401 immediately; token validity (existence, revocation, expiration, and scope)
    is enforced by SmartPot-API on each request. Passes `lifespan` scopes through so startup is unaffected.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in PUBLIC_PATHS or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        token = None
        for key, value in scope.get("headers", []):
            if key == b"authorization":
                raw = value.decode("latin-1")
                if raw.startswith("Bearer "):
                    token = raw[len("Bearer ") :].strip()
                break
        if not is_connection_token(token):
            body = (
                '{"error":"Missing connection token. Create one in SmartPot under Profile › Connections '
                'and send it as Authorization: Bearer spt_…"}'
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"www-authenticate", b'Bearer realm="smartpot"'),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
