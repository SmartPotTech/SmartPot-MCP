"""SmartPot MCP server configuration (environment variables) and authority parsing."""

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """MCP server settings. All values are read from environment variables or a local `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # SmartPot-API. El servidor no tiene cuenta propia: cada petición usa el token de conexión de quien se conecta
    # (cabecera Authorization en HTTP). En stdio, que es local y de una sola persona, el token va en el entorno.
    api_url: str = Field(default="http://localhost:8091", alias="SMARTPOT_API_URL")
    api_token: str | None = Field(default=None, alias="SMARTPOT_API_TOKEN")
    timeout_seconds: float = Field(default=15.0, alias="TIMEOUT_SECONDS")

    # Transporte: stdio para clientes locales; streamable-http para el contenedor.
    transport: Literal["stdio", "streamable-http"] = Field(default="stdio", alias="TRANSPORT")
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8002, alias="PORT")
    mcp_path: str = Field(default="/mcp", alias="MCP_PATH")

    # Protección contra DNS rebinding del transporte HTTP: Host y Origin permitidos (separados por comas).
    allowed_hosts: str = Field(
        default="localhost:*,127.0.0.1:*,[::1]:*",
        alias="MCP_ALLOWED_HOSTS",
    )
    allowed_origins: str = Field(
        default=("http://localhost:*,http://127.0.0.1:*,http://[::1]:*,https://smartpot.app,https://www.smartpot.app"),
        alias="MCP_ALLOWED_ORIGINS",
    )

    # Validez real del token contra la API: caché en memoria por hash SHA-256 (segundos).
    token_cache_seconds: float = Field(default=30.0, ge=0.0, alias="MCP_TOKEN_CACHE_SECONDS")

    # Límite de filas que una herramienta puede traer de una vez (protege el contexto del modelo).
    max_rows: int = Field(default=500, alias="MCP_MAX_ROWS")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @staticmethod
    def split(raw: str) -> list[str]:
        items = [item.strip() for item in raw.split(",") if item.strip()]
        result: list[str] = []
        for item in items:
            if item not in result:
                result.append(item)
        return result


def parse_authority(value: str | None) -> tuple[str, int | None] | None:
    """Parses `host[:port]` (including IPv6 brackets) and rejects anything ambiguous."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or any(character.isspace() for character in text):
        return None
    if text.endswith(":") or any(character in text for character in "/\\@?#,"):
        return None
    try:
        parsed = urlsplit("//" + text)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if host is None or parsed.path or parsed.query or parsed.fragment:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if port is not None and not 1 <= port <= 65535:
        return None
    return host.lower(), port


def _host_pattern(pattern: str) -> tuple[str, int | None, bool] | None:
    raw = pattern.strip().lower()
    wildcard_port = raw.endswith(":*")
    if wildcard_port:
        raw = raw[:-2]
    if "*" in raw:
        if not raw.startswith("*."):
            return None
        base = raw[2:]
        if not base or "*" in base:
            return None
        return "*." + base, None, wildcard_port
    parsed = parse_authority(raw)
    if parsed is None:
        return None
    host, port = parsed
    return host, port, wildcard_port


def is_allowed_host(header: str | None, patterns: list[str]) -> bool:
    """Exact host matching with optional `:*` port wildcard and `*.` subdomain wildcard."""
    parsed = parse_authority(header)
    if parsed is None:
        return False
    host, port = parsed
    for pattern in patterns:
        candidate = _host_pattern(pattern)
        if candidate is None:
            continue
        allowed_host, allowed_port, wildcard = candidate
        if allowed_host.startswith("*."):
            base = allowed_host[2:]
            if host != base and not host.endswith("." + base):
                continue
        elif host != allowed_host:
            continue
        if wildcard or allowed_port is None or port == allowed_port:
            return True
    return False


def _origin_parts(value: str | None) -> tuple[str, str, int] | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or any(character.isspace() for character in text):
        return None
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or parsed.hostname is None:
        return None
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    if not 1 <= port <= 65535:
        return None
    return parsed.scheme, parsed.hostname.lower(), port


def _origin_pattern(pattern: str) -> tuple[str, str, int | None, bool] | None:
    raw = pattern.strip().lower()
    wildcard = raw.endswith(":*")
    if wildcard:
        raw = raw[:-2]
    parts = _origin_parts(raw)
    if parts is None:
        return None
    scheme, host, port = parts
    return scheme, host, None if wildcard else port, wildcard


def is_allowed_origin(origin: str | None, patterns: list[str]) -> bool:
    """Matches an absolute http(s) origin, including `:*` port wildcards."""
    if not origin:
        return True  # Los clientes MCP no navegador pueden no enviar Origin.
    parts = _origin_parts(origin)
    if parts is None:
        return False
    scheme, host, port = parts
    for pattern in patterns:
        candidate = _origin_pattern(pattern)
        if candidate is None:
            continue
        allowed_scheme, allowed_host, allowed_port, wildcard = candidate
        if scheme != allowed_scheme or host != allowed_host:
            continue
        if wildcard or allowed_port is None or port == allowed_port:
            return True
    return False


def static_origins(patterns: list[str]) -> list[str]:
    """Exact origins for Starlette's allow_origins; wildcard entries go to the regex."""
    return [pattern for pattern in patterns if not pattern.endswith(":*") and "*" not in pattern]


def origin_regex(patterns: list[str]) -> str | None:
    """Regex for wildcard origins, because Starlette does not understand `:*` in allow_origins."""
    expressions: list[str] = []
    for pattern in patterns:
        candidate = _origin_pattern(pattern)
        if candidate is None:
            continue
        scheme, host, port, wildcard = candidate
        if "*" in host:
            base = host.removeprefix("*.")
            host_expression = rf"([a-z0-9-]+\.)*{re.escape(base)}"
        else:
            host_expression = re.escape(host)
        if wildcard:
            expressions.append(rf"{re.escape(scheme)}://{host_expression}(:\d{{1,5}})?")
        elif port in (80, 443):
            expressions.append(rf"{re.escape(scheme)}://{host_expression}(:{port})?")
        else:
            expressions.append(rf"{re.escape(scheme)}://{host_expression}:{port}")
    if not expressions:
        return None
    return r"^(?:" + "|".join(expressions) + r")$"


settings = Settings()
