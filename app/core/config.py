"""SmartPot MCP server configuration (environment variables)."""

from typing import Literal

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
    allowed_hosts: str = Field(default="localhost:*,127.0.0.1:*", alias="MCP_ALLOWED_HOSTS")
    allowed_origins: str = Field(
        default="http://localhost:*,http://127.0.0.1:*,https://smartpot.app,https://www.smartpot.app",
        alias="MCP_ALLOWED_ORIGINS",
    )

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
            if item.endswith(":*"):
                base = item[:-2]
                if base and base not in result:
                    result.append(base)
        return result


settings = Settings()
