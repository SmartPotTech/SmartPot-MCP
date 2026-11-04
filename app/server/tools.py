"""SmartPot MCP tools registered via the `@mcp.tool()` decorator.

Each tool declares annotations (read-only, destructive, idempotent) so the MCP client prompts for
confirmation before executing actions with physical or irreversible effects.
"""

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from app.client.api_client import SmartPotClient
from app.core.config import settings
from app.server.auth import user_api

CropType = Literal["TOMATO", "LETTUCE", "STRAWBERRY", "BASIL", "SPINACH", "PEPPER"]
CropForm = Literal["POT", "NFT", "TOWER", "RAFT"]
Setting = Literal["INDOOR", "OUTDOOR"]
Exposure = Literal["FULL_SUN", "PARTIAL_SUN", "SHADE"]
ActuatorType = Literal["WATER_PUMP", "UV_LIGHT", "FAN", "HUMIDIFIER", "NUTRIENT_DOSER", "PH_DOSER"]
Action = Literal["ACTIVATE", "DEACTIVATE"]
Metric = Literal["temperature", "humidity", "brightness", "ph", "tds", "soilMoisture", "atmosphere"]

ObjectId = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{24}$", description="24-character hexadecimal identifier")]
Hours = Annotated[int, Field(ge=1, le=168, description="Window in hours (1 to 168)")]
Duration = Annotated[int, Field(ge=1, le=3600, description="Duration in seconds (1 to 3600)")]

READ = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
IDEMPOTENT = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
PHYSICAL = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False)


def _placement(
    setting: str | None, exposure: str | None, place: str | None, lat: float | None, lon: float | None
) -> dict[str, Any] | None:
    if setting is None and exposure is None and lat is None and lon is None:
        return None
    placement: dict[str, Any] = {}
    if setting:
        placement["setting"] = setting
    if exposure:
        placement["exposure"] = exposure
    if lat is not None and lon is not None:
        placement["location"] = {"name": place or "", "latitude": lat, "longitude": lon}
    return placement


def register_tools(mcp: MCPServer, client: SmartPotClient) -> None:
    """Registers all MCP tools on the API client."""

    # ---------------------------------------------------------------- Cuenta

    @mcp.tool(name="get_account", title="Connected account", annotations=READ)
    async def get_account(ctx: Context) -> dict[str, Any]:
        """Returns the name and email of the SmartPot account that owns this connection."""
        me = await user_api(client, ctx).me()
        return {k: me.get(k) for k in ("id", "name", "lastName", "email") if isinstance(me, dict)}

    # ---------------------------------------------------------------- Cultivos

    @mcp.tool(name="list_crops", title="List crops", annotations=READ)
    async def list_crops(ctx: Context) -> list[dict[str, Any]]:
        """Lists the account's crops with species, form, health, device status, and latest reading."""
        return await user_api(client, ctx).list_crops()

    @mcp.tool(name="get_crop", title="Get crop", annotations=READ)
    async def get_crop(ctx: Context, crop_id: ObjectId) -> dict[str, Any]:
        """Returns detailed information for a crop: placement, automation, health, and latest reading."""
        return await user_api(client, ctx).get_crop(crop_id)

    @mcp.tool(name="create_crop", title="Create crop", annotations=WRITE)
    async def create_crop(
        ctx: Context,
        name: Annotated[str, Field(min_length=2, max_length=60)],
        crop_type: CropType,
        kind: Literal["REAL", "VIRTUAL"] = "VIRTUAL",
        form: CropForm | None = None,
        setting: Setting | None = None,
        exposure: Exposure | None = None,
        place_name: str | None = None,
        latitude: Annotated[float, Field(ge=-90, le=90)] | None = None,
        longitude: Annotated[float, Field(ge=-180, le=180)] | None = None,
        virtual_mode: Literal["AUTO", "MANUAL", "WEATHER"] = "AUTO",
        virtual_interval_seconds: Annotated[int, Field(ge=5, le=3600)] = 15,
    ) -> dict[str, Any]:
        """Creates a crop. VIRTUAL is fed by the simulator; REAL returns one-time device MQTT credentials,
        which the server redacts from the model."""
        payload: dict[str, Any] = {"name": name, "type": crop_type, "kind": kind}
        if form:
            payload["form"] = form
        placement = _placement(setting, exposure, place_name, latitude, longitude)
        if placement:
            payload["placement"] = placement
        if kind == "VIRTUAL":
            payload["virtual"] = {"mode": virtual_mode, "intervalSeconds": virtual_interval_seconds}
        created = await user_api(client, ctx).create_crop(payload)
        if isinstance(created, dict) and created.get("device"):
            created["device"] = {"note": "Credentials issued: view them in the PWA, never exposed via MCP"}
        return created

    @mcp.tool(name="update_crop", title="Update crop", annotations=IDEMPOTENT)
    async def update_crop(
        ctx: Context,
        crop_id: ObjectId,
        name: Annotated[str, Field(min_length=2, max_length=60)] | None = None,
        crop_type: CropType | None = None,
        form: CropForm | None = None,
        setting: Setting | None = None,
        exposure: Exposure | None = None,
        place_name: str | None = None,
        latitude: Annotated[float, Field(ge=-90, le=90)] | None = None,
        longitude: Annotated[float, Field(ge=-180, le=180)] | None = None,
    ) -> dict[str, Any]:
        """Updates crop name, species, form, or placement. Omitted fields keep their current value."""
        current = await user_api(client, ctx).get_crop(crop_id)
        payload: dict[str, Any] = {
            "name": name or current.get("name"),
            "type": crop_type or current.get("type"),
            "form": form or current.get("form"),
        }
        placement = _placement(setting, exposure, place_name, latitude, longitude)
        if placement:
            payload["placement"] = placement
        return await user_api(client, ctx).update_crop(crop_id, payload)

    @mcp.tool(name="delete_crop", title="Delete crop", annotations=DESTRUCTIVE)
    async def delete_crop(ctx: Context, crop_id: ObjectId) -> dict[str, str]:
        """Deletes the crop along with its readings, commands, actuators, and notifications. Irreversible."""
        await user_api(client, ctx).delete_crop(crop_id)
        return {"status": "DELETED", "cropId": crop_id}

    @mcp.tool(name="set_crop_automation", title="Enable or pause automation", annotations=IDEMPOTENT)
    async def set_crop_automation(ctx: Context, crop_id: ObjectId, enabled: bool) -> Any:
        """Enables or pauses the autonomous agent that triggers crop actuators based on AI recommendations."""
        return await user_api(client, ctx).set_automation(crop_id, enabled)

    @mcp.tool(name="get_crop_weather", title="Crop weather", annotations=READ)
    async def get_crop_weather(ctx: Context, crop_id: ObjectId) -> Any:
        """Current weather at the crop's location (requires the crop to have coordinates configured)."""
        return await user_api(client, ctx).crop_weather(crop_id)

    # ---------------------------------------------------------------- Lecturas

    @mcp.tool(name="get_latest_reading", title="Latest reading", annotations=READ)
    async def get_latest_reading(ctx: Context, crop_id: ObjectId) -> dict[str, Any]:
        """Latest reading: temperature, humidity, light, pH, TDS, atmospheric pressure, and substrate moisture."""
        return await user_api(client, ctx).latest_reading(crop_id)

    @mcp.tool(name="get_readings_history", title="Readings history", annotations=READ)
    async def get_readings_history(
        ctx: Context,
        crop_id: ObjectId,
        from_time: Annotated[str, Field(description="RFC 3339 start, e.g. 2026-10-31T00:00:00Z")] | None = None,
        to_time: Annotated[str, Field(description="RFC 3339 end")] | None = None,
        limit: Annotated[int, Field(ge=1)] = 100,
    ) -> list[dict[str, Any]]:
        """Crop readings within a date range, ordered from newest to oldest."""
        return await user_api(client, ctx).readings(crop_id, from_time, to_time, min(limit, settings.max_rows))

    @mcp.tool(name="get_readings_summary", title="Readings summary", annotations=READ)
    async def get_readings_summary(ctx: Context, crop_id: ObjectId, hours: Hours = 24) -> dict[str, Any]:
        """Minimum, average, and maximum of each variable over the last N hours."""
        return await user_api(client, ctx).readings_summary(crop_id, hours)

    @mcp.tool(name="record_reading", title="Record manual reading", annotations=WRITE)
    async def record_reading(
        ctx: Context,
        crop_id: ObjectId,
        temperature: float | None = None,
        humidity: Annotated[float, Field(ge=0, le=100)] | None = None,
        brightness: Annotated[float, Field(ge=0)] | None = None,
        ph: Annotated[float, Field(ge=0, le=14)] | None = None,
        tds: Annotated[float, Field(ge=0)] | None = None,
        atmosphere: Annotated[float, Field(ge=0)] | None = None,
        soil_moisture: Annotated[float, Field(ge=0, le=100)] | None = None,
    ) -> dict[str, Any]:
        """Records a manually measured reading (at least one variable required)."""
        measures = {
            k: v
            for k, v in {
                "temperature": temperature,
                "humidity": humidity,
                "brightness": brightness,
                "ph": ph,
                "tds": tds,
                "atmosphere": atmosphere,
                "soilMoisture": soil_moisture,
            }.items()
            if v is not None
        }
        if not measures:
            raise ValueError("Provide at least one measured variable")
        return await user_api(client, ctx).record_reading(crop_id, measures)

    # ---------------------------------------------------------------- Actuadores y comandos

    @mcp.tool(name="list_actuators", title="Crop actuators", annotations=READ)
    async def list_actuators(ctx: Context, crop_id: ObjectId) -> list[dict[str, Any]]:
        """Lists the crop's actuators (pump, UV light, fan, humidifier, dosers) and whether they are active."""
        return await user_api(client, ctx).actuators(crop_id)

    @mcp.tool(name="send_actuator_command", title="Trigger actuator", annotations=PHYSICAL)
    async def send_actuator_command(
        ctx: Context, crop_id: ObjectId, actuator_id: ObjectId, action: Action, duration_seconds: Duration | None = None
    ) -> dict[str, Any]:
        """Turns an actuator on or off over MQTT. Drives physical hardware on REAL crops: confirm first."""
        return await user_api(client, ctx).send_command(crop_id, actuator_id, action, duration_seconds)

    @mcp.tool(name="send_bulk_command", title="Trigger multiple crops", annotations=PHYSICAL)
    async def send_bulk_command(
        ctx: Context,
        crop_ids: Annotated[list[ObjectId], Field(min_length=1, max_length=50)],
        actuator_type: ActuatorType,
        action: Action,
        duration_seconds: Duration | None = None,
    ) -> dict[str, Any]:
        """Triggers the same actuator type across multiple crops; returns sent, skipped, and failed items."""
        return await user_api(client, ctx).send_bulk_command(crop_ids, actuator_type, action, duration_seconds)

    @mcp.tool(name="list_commands", title="Command history", annotations=READ)
    async def list_commands(
        ctx: Context, crop_id: ObjectId, limit: Annotated[int, Field(ge=1, le=200)] = 30
    ) -> list[dict[str, Any]]:
        """Recent commands for the crop with status (PENDING, SENT, EXECUTED, FAILED, EXPIRED) and source."""
        return await user_api(client, ctx).crop_commands(crop_id, limit)

    # ---------------------------------------------------------------- IA

    @mcp.tool(name="get_crop_insights", title="AI diagnosis", annotations=READ)
    async def get_crop_insights(ctx: Context, crop_id: ObjectId) -> dict[str, Any]:
        """SmartPot-AI diagnosis: 0-100 health index, conclusions, suggested actions, and forecast."""
        return await user_api(client, ctx).insights(crop_id)

    @mcp.tool(name="get_crop_profiles", title="Crop profiles", annotations=READ)
    async def get_crop_profiles() -> Any:
        """Recommended optimal ranges per crop species."""
        return await client.crop_profiles()

    @mcp.tool(name="get_learning_status", title="Learning status", annotations=READ)
    async def get_learning_status(ctx: Context) -> Any:
        """Continuous AI learning status (sample counts and model versions)."""
        return await user_api(client, ctx).learning_status()

    # ---------------------------------------------------------------- Panel general

    @mcp.tool(name="get_overview", title="General overview", annotations=READ)
    async def get_overview(ctx: Context) -> dict[str, Any]:
        """Account summary: crops, health, online devices, commands, and notifications."""
        return await user_api(client, ctx).overview()

    @mcp.tool(name="get_metric_series", title="Metric time series", annotations=READ)
    async def get_metric_series(ctx: Context, metric: Metric = "temperature", hours: Hours = 24) -> dict[str, Any]:
        """Interval averages of a metric across all crops (TimescaleDB aggregates)."""
        return await user_api(client, ctx).series(metric, hours)

    @mcp.tool(name="get_fleet", title="Fleet analysis", annotations=READ)
    async def get_fleet(ctx: Context) -> Any:
        """Cross-crop comparison across all crops in the account."""
        return await user_api(client, ctx).fleet()

    # ---------------------------------------------------------------- Notificaciones

    @mcp.tool(name="list_notifications", title="Notifications", annotations=READ)
    async def list_notifications(ctx: Context) -> Any:
        """Account notifications (AI alerts, commands, device events)."""
        return await user_api(client, ctx).notifications()

    @mcp.tool(name="get_unread_count", title="Unread notification count", annotations=READ)
    async def get_unread_count(ctx: Context) -> Any:
        """Number of unread notifications."""
        return await user_api(client, ctx).unread_count()

    @mcp.tool(name="mark_notification_read", title="Mark notification as read", annotations=IDEMPOTENT)
    async def mark_notification_read(ctx: Context, notification_id: ObjectId) -> Any:
        """Marks a notification as read."""
        return await user_api(client, ctx).mark_read(notification_id)
