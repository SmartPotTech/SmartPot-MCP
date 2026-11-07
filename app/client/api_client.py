"""Asynchronous SmartPot-API client with a shared connection pool.

The server has no service account of its own: each call uses the connected user's connection token so the API
enforces their crops and selected scope (read-only or control). Tools never accept or return raw tokens.
"""

from collections.abc import Callable
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from app.core.config import settings
from app.core.logging import logger
from app.core.security import require_object_id


class SmartPotAPIError(ToolError):
    """Error returned by SmartPot-API. Inherits from ToolError so the API message reaches the model
    (the SDK hides the text of any other exception)."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class SmartPotClient:
    """Shared HTTP pool toward the API; `for_token` returns a user-scoped view."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.api_url).rstrip("/")
        self._timeout = timeout or settings.timeout_seconds
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        # El middleware HTTP registra aquí la invalidación de la caché de tokens cuando la API responde 401.
        self.on_unauthorized: Callable[[str], None] | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self._timeout, connect=5.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
                headers={"Accept": "application/json", "User-Agent": "SmartPot-MCP/1.0"},
                transport=self._transport,
                follow_redirects=False,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def for_token(self, token: str) -> "UserAPI":
        return UserAPI(self, token)

    async def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else None
        try:
            resp = await self._http().request(method, path, params=params, json=json_body, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("Network error calling SmartPot-API on %s %s: %s", method, path, type(exc).__name__)
            raise SmartPotAPIError(503, "SmartPot-API is unavailable") from exc
        if resp.is_error:
            # Un 401 demuestra que el token dejó de ser válido (revocado o expirado): la caché no puede
            # seguir aceptándolo durante el TTL restante.
            if resp.status_code == 401 and token and self.on_unauthorized is not None:
                self.on_unauthorized(token)
            raise SmartPotAPIError(resp.status_code, _error_message(resp))
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # --- Públicas (sin token) ---
    async def health(self) -> dict[str, Any]:
        return await self.request("GET", "/health")

    async def crop_profiles(self) -> Any:
        return await self.request("GET", "/api/v1/crop-profiles")


class UserAPI:
    """API operations executed on behalf of a user (using their connection token)."""

    def __init__(self, client: SmartPotClient, token: str) -> None:
        self._client = client
        self._token = token

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        return await self._client.request(method, path, token=self._token, **kwargs)

    @staticmethod
    def _crop(crop_id: str) -> str:
        return f"/api/v1/crops/{require_object_id(crop_id, 'crop_id')}"

    async def crop_profiles(self) -> Any:
        return await self._client.crop_profiles()

    # --- Cuenta ---
    async def me(self) -> dict[str, Any]:
        return await self._call("GET", "/api/v1/users/me")

    # --- Cultivos ---
    async def list_crops(self) -> list[dict[str, Any]]:
        return await self._call("GET", "/api/v1/crops")

    async def get_crop(self, crop_id: str) -> dict[str, Any]:
        return await self._call("GET", self._crop(crop_id))

    async def create_crop(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._call("POST", "/api/v1/crops", json_body=payload)

    async def update_crop(self, crop_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._call("PUT", self._crop(crop_id), json_body=payload)

    async def delete_crop(self, crop_id: str) -> None:
        await self._call("DELETE", self._crop(crop_id))

    async def set_automation(self, crop_id: str, enabled: bool) -> Any:
        return await self._call("PUT", f"{self._crop(crop_id)}/automation", json_body={"enabled": enabled})

    async def crop_weather(self, crop_id: str) -> Any:
        return await self._call("GET", f"{self._crop(crop_id)}/weather")

    # --- Lecturas ---
    async def latest_reading(self, crop_id: str) -> dict[str, Any]:
        return await self._call("GET", f"{self._crop(crop_id)}/readings/latest")

    async def readings(self, crop_id: str, from_time: str | None, to_time: str | None, limit: int) -> Any:
        params: dict[str, Any] = {"limit": limit}
        if from_time:
            params["from"] = from_time
        if to_time:
            params["to"] = to_time
        return await self._call("GET", f"{self._crop(crop_id)}/readings", params=params)

    async def readings_summary(self, crop_id: str, hours: int) -> dict[str, Any]:
        return await self._call("GET", f"{self._crop(crop_id)}/readings/summary", params={"hours": hours})

    async def record_reading(self, crop_id: str, measures: dict[str, float]) -> dict[str, Any]:
        return await self._call("POST", f"{self._crop(crop_id)}/readings", json_body=measures)

    # --- Actuadores y comandos ---
    async def actuators(self, crop_id: str) -> list[dict[str, Any]]:
        return await self._call("GET", f"{self._crop(crop_id)}/actuators")

    async def send_command(
        self, crop_id: str, actuator_id: str, action: str, duration_seconds: int | None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"actuatorId": require_object_id(actuator_id, "actuator_id"), "action": action}
        if duration_seconds is not None:
            body["durationSeconds"] = duration_seconds
        return await self._call("POST", f"{self._crop(crop_id)}/commands", json_body=body)

    async def send_bulk_command(
        self, crop_ids: list[str], actuator_type: str, action: str, duration_seconds: int | None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "cropIds": [require_object_id(c, "crop_ids") for c in crop_ids],
            "actuatorType": actuator_type,
            "action": action,
        }
        if duration_seconds is not None:
            body["durationSeconds"] = duration_seconds
        return await self._call("POST", "/api/v1/commands/bulk", json_body=body)

    async def crop_commands(self, crop_id: str, limit: int) -> Any:
        return await self._call("GET", f"{self._crop(crop_id)}/commands", params={"limit": limit})

    # --- IA ---
    async def insights(self, crop_id: str) -> dict[str, Any]:
        return await self._call("GET", f"{self._crop(crop_id)}/insights")

    async def learning_status(self) -> Any:
        return await self._call("GET", "/api/v1/ai/learning")

    # --- Panel general ---
    async def overview(self) -> dict[str, Any]:
        return await self._call("GET", "/api/v1/overview")

    async def series(self, metric: str, hours: int) -> dict[str, Any]:
        return await self._call("GET", "/api/v1/overview/series", params={"metric": metric, "hours": hours})

    async def fleet(self) -> Any:
        return await self._call("GET", "/api/v1/overview/fleet")

    # --- Notificaciones ---
    async def notifications(self) -> Any:
        return await self._call("GET", "/api/v1/notifications")

    async def unread_count(self) -> Any:
        return await self._call("GET", "/api/v1/notifications/unread-count")

    async def mark_read(self, notification_id: str) -> Any:
        path = f"/api/v1/notifications/{require_object_id(notification_id, 'notification_id')}/read"
        return await self._call("PUT", path)


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return f"SmartPot-API returned HTTP {resp.status_code}"
    if isinstance(body, dict):
        return str(body.get("message") or body.get("error") or f"SmartPot-API returned HTTP {resp.status_code}")
    return f"SmartPot-API returned HTTP {resp.status_code}"
