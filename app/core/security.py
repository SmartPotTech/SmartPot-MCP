"""Security controls: identifiers, connection tokens and HTTP authority validation."""

import asyncio
import hashlib
import json
import re
import time
from collections import OrderedDict
from collections.abc import Mapping

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import is_allowed_host, is_allowed_origin

# Los identificadores de SmartPot son ObjectId de 24 caracteres hexadecimales. Validarlos impide que un
# argumento manipulado (p. ej. "../../users/me") cambie la ruta de la API a la que llama el servidor.
_OBJECT_ID = re.compile(r"^[0-9a-fA-F]{24}$")

# Los tokens de conexión que emite SmartPot-API empiezan así; un JWT de sesión no sirve para conectarse.
CONNECTION_TOKEN_PREFIX = "spt_"
_CONNECTION_TOKEN = re.compile(r"^spt_[A-Za-z0-9_-]{20,128}$")

PUBLIC_PATHS = frozenset({"/health", "/livez"})
CACHE_LIMIT = 1024
NEGATIVE_CACHE_MAX_TTL = 5.0
_MAX_DRAIN_BYTES = 65_536


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
    body = json.dumps({"error": message}).encode("utf-8")
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
        self._cache: OrderedDict[str, tuple[float, float, bool]] = OrderedDict()
        self._cache_lock = asyncio.Lock()
        self._inflight: dict[str, tuple[asyncio.Lock, int]] = {}

    def invalidate(self, token: str) -> None:
        """Drops a cached verdict after the API rejected the token (revoked or expired)."""
        self._cache.pop(hashlib.sha256(token.encode("utf-8")).hexdigest(), None)

    def _cached(self, key: str, now: float) -> bool | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, entry_ttl, verdict = entry
        if now - ts > entry_ttl:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return verdict

    async def valid(self, token: str) -> bool | None:
        if self.client is None:
            return None
        key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.monotonic()
        cached = self._cached(key, now)
        if cached is not None:
            return cached

        async with self._cache_lock:
            token_lock, waiters = self._inflight.get(key) or (asyncio.Lock(), 0)
            self._inflight[key] = (token_lock, waiters + 1)

        try:
            async with token_lock:
                cached = self._cached(key, time.monotonic())
                if cached is not None:
                    return cached
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
                    entry_ttl = self.ttl if result else min(self.ttl, NEGATIVE_CACHE_MAX_TTL)
                    async with self._cache_lock:
                        while len(self._cache) >= CACHE_LIMIT:
                            self._cache.popitem(last=False)
                        self._cache[key] = (time.monotonic(), entry_ttl, result)
                        self._cache.move_to_end(key)
                return result
        finally:
            async with self._cache_lock:
                lock_ref, remaining = self._inflight[key]
                if remaining <= 1:
                    self._inflight.pop(key, None)
                else:
                    self._inflight[key] = (lock_ref, remaining - 1)


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
            await _reject(scope, receive, send, 421, "Host is not allowed")
            return
        origin = headers.get("origin")
        if origin and not is_allowed_origin(origin, self.allowed_origins):
            await _reject(scope, receive, send, 403, "Origin is not allowed")
            return
        await self.app(scope, receive, send)


def _has_request_body(scope: Scope) -> bool:
    if scope.get("method", "").upper() in ("GET", "HEAD", "OPTIONS", "DELETE"):
        return False
    for key, value in scope.get("headers", []):
        name = key.lower()
        if name == b"transfer-encoding":
            return True
        if name == b"content-length":
            try:
                return int(value) > 0
            except ValueError:
                return True
    return False


async def _reject(
    scope: Scope,
    receive: Receive,
    send: Send,
    status: int,
    message: str,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    if _has_request_body(scope):
        drained = 0
        while drained < _MAX_DRAIN_BYTES:
            chunk = await receive()
            if chunk.get("type") != "http.request":
                break
            drained += len(chunk.get("body", b""))
            if not chunk.get("more_body", False):
                break
    code, body, extra = _response(status, message, headers)
    await send({"type": "http.response.start", "status": code, "headers": extra})
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
            if key.lower() == b"authorization":
                raw = value.decode("latin-1")
                if raw.startswith("Bearer "):
                    token = raw[len("Bearer ") :].strip()
                break
        if not is_connection_token(token):
            await _reject(
                scope,
                receive,
                send,
                401,
                "Missing connection token. Create one in SmartPot under Profile › Connections "
                "and send it as Authorization: Bearer spt_...",
                [(b"www-authenticate", b'Bearer realm="smartpot"')],
            )
            return
        valid = await self.validator.valid(token)
        if valid is False:
            await _reject(
                scope,
                receive,
                send,
                401,
                "The connection token is invalid or has been revoked",
                [(b"www-authenticate", b'Bearer realm="smartpot"')],
            )
            return
        if valid is None:
            await _reject(scope, receive, send, 503, "Connection token could not be validated")
            return
        await self.app(scope, receive, send)
