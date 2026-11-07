"""Security controls: identifiers, connection tokens and HTTP authority validation."""

import asyncio
import hashlib
import re
import time
from collections.abc import Mapping

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import is_allowed_host, is_allowed_origin

# Los identificadores de SmartPot son ObjectId de 24 caracteres hexadecimales. Validarlos impide que un
# argumento manipulado (p. ej. "../../users/me") cambie la ruta de la API a la que llama el servidor.
_OBJECT_ID = re.compile(r"^[0-9a-fA-F]{24}$")

# Los tokens de conexión que emite SmartPot-API empiezan así; un JWT de sesión no sirve para conectarse.
CONNECTION_TOKEN_PREFIX = "spt_"
_CONNECTION_TOKEN = re.compile(r"^spt_[A-Za-z0-9_-]{20,128}$")

PUBLIC_PATHS = frozenset({"/health"})
CACHE_LIMIT = 1024


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


def _response(
    status: int, message: str, headers: list[tuple[bytes, bytes]] | None = None
) -> tuple[int, bytes, list[tuple[bytes, bytes]]]:
    body = ('{"error":"' + message.replace('"', "'") + '"}').encode()
    extra = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode()),
    ]
    return status, body, extra + (headers or [])


class TokenValidator:
    """Checks `spt_` tokens against SmartPot-API and caches the verdict for a short TTL."""

    def __init__(self, client, ttl_seconds: float = 30.0) -> None:
        self.client = client
        self.ttl = max(0.0, ttl_seconds)
        self._cache: dict[str, tuple[float, bool]] = {}
        self._lock = asyncio.Lock()

    def invalidate(self, token: str) -> None:
        """Drops a cached verdict after the API rejected the token (revoked or expired)."""
        self._cache.pop(hashlib.sha256(token.encode("utf-8")).hexdigest(), None)

    async def valid(self, token: str) -> bool | None:
        if self.client is None:
            return None
        key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and now - cached[0] <= self.ttl:
            return cached[1]
        async with self._lock:
            cached = self._cache.get(key)
            if cached is not None and now - cached[0] <= self.ttl:
                return cached[1]
            result: bool | None
            try:
                await self.client.for_token(token).me()
                result = True
            except Exception as error:  # noqa: BLE001
                status = getattr(error, "status_code", None)
                if status in (401, 403):
                    result = False
                else:
                    # 5xx o red caída: no se cachea y se responde 503 para no aceptar un token sin verificar.
                    return None
            if self.ttl > 0:
                while len(self._cache) >= CACHE_LIMIT:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[key] = (time.monotonic(), result)
            return result


class AuthorityValidationMiddleware:
    """Strict Host/Origin validation before the token is sent to the API."""

    def __init__(self, app: ASGIApp, allowed_hosts: list[str], allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed_hosts = allowed_hosts
        self.allowed_origins = allowed_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in PUBLIC_PATHS or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        headers: dict[str, str] = {}
        host_count = 0
        for key, value in scope.get("headers", []):
            name = key.decode("latin-1").lower()
            if name == "host":
                host_count += 1
                if host_count > 1:
                    break
            headers.setdefault(name, value.decode("latin-1"))
        if host_count != 1 or not is_allowed_host(headers.get("host"), self.allowed_hosts):
            status, body, extra = _response(421, "Host is not allowed")
            await _send(send, status, body, extra)
            return
        origin = headers.get("origin")
        if origin and not is_allowed_origin(origin, self.allowed_origins):
            status, body, extra = _response(403, "Origin is not allowed")
            await _send(send, status, body, extra)
            return
        await self.app(scope, receive, send)


async def _send(send: Send, status: int, body: bytes, headers: list[tuple[bytes, bytes]]) -> None:
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class ConnectionTokenMiddleware:
    """Requires a valid SmartPot connection token on all HTTP routes except public endpoints.

    The format is checked before touching the API; a well-formed but fake or revoked token is
    rejected with 401 on every route, including `tools/list`.
    """

    def __init__(self, app: ASGIApp, validator: TokenValidator) -> None:
        self.app = app
        self.validator = validator

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
            status, body, extra = _response(
                401,
                "Missing connection token. Create one in SmartPot under Profile › Connections "
                "and send it as Authorization: Bearer spt_...",
                [(b"www-authenticate", b'Bearer realm="smartpot"')],
            )
            await _send(send, status, body, extra)
            return
        valid = await self.validator.valid(token)
        if valid is False:
            status, body, extra = _response(
                401,
                "The connection token is invalid or has been revoked",
                [(b"www-authenticate", b'Bearer realm="smartpot"')],
            )
            await _send(send, status, body, extra)
            return
        if valid is None:
            status, body, extra = _response(503, "Connection token could not be validated")
            await _send(send, status, body, extra)
            return
        await self.app(scope, receive, send)
