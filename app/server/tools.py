"""Herramientas MCP de SmartPot, registradas con el decorador `@mcp.tool()`.

Cada herramienta declara anotaciones (solo lectura, destructiva, idempotente) para que el cliente MCP pida
confirmación antes de acciones con efecto físico o irreversible.
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

ObjectId = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{24}$", description="Identificador de 24 caracteres hex")]
Hours = Annotated[int, Field(ge=1, le=168, description="Ventana en horas (1 a 168)")]
Duration = Annotated[int, Field(ge=1, le=3600, description="Duración en segundos (1 a 3600)")]

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
    """Registra las herramientas sobre el cliente de la API."""

    # ---------------------------------------------------------------- Cuenta

    @mcp.tool(name="get_account", title="Cuenta conectada", annotations=READ)
    async def get_account(ctx: Context) -> dict[str, Any]:
        """Nombre y correo de la cuenta de SmartPot a la que pertenece esta conexión."""
        me = await user_api(client, ctx).me()
        return {k: me.get(k) for k in ("id", "name", "lastName", "email") if isinstance(me, dict)}

    # ---------------------------------------------------------------- Cultivos

    @mcp.tool(name="list_crops", title="Listar cultivos", annotations=READ)
    async def list_crops(ctx: Context) -> list[dict[str, Any]]:
        """Lista los cultivos de la cuenta con tipo, forma, salud, estado del dispositivo y última lectura."""
        return await user_api(client, ctx).list_crops()

    @mcp.tool(name="get_crop", title="Ver un cultivo", annotations=READ)
    async def get_crop(ctx: Context, crop_id: ObjectId) -> dict[str, Any]:
        """Devuelve el detalle de un cultivo: lugar, automatización, salud y última lectura."""
        return await user_api(client, ctx).get_crop(crop_id)

    @mcp.tool(name="create_crop", title="Crear un cultivo", annotations=WRITE)
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
        """Crea un cultivo. VIRTUAL lo alimenta el simulador; REAL devuelve una sola vez las credenciales MQTT
        del dispositivo, que el servidor oculta al modelo."""
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
            created["device"] = {"note": "Credenciales entregadas: consúltalas en la PWA, no se exponen por MCP"}
        return created

    @mcp.tool(name="update_crop", title="Editar un cultivo", annotations=IDEMPOTENT)
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
        """Cambia nombre, tipo, forma o lugar del cultivo. Los campos omitidos conservan su valor actual."""
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

    @mcp.tool(name="delete_crop", title="Eliminar un cultivo", annotations=DESTRUCTIVE)
    async def delete_crop(ctx: Context, crop_id: ObjectId) -> dict[str, str]:
        """Elimina el cultivo con sus lecturas, comandos, actuadores y avisos. No se puede deshacer."""
        await user_api(client, ctx).delete_crop(crop_id)
        return {"status": "DELETED", "cropId": crop_id}

    @mcp.tool(name="set_crop_automation", title="Activar o pausar el automático", annotations=IDEMPOTENT)
    async def set_crop_automation(ctx: Context, crop_id: ObjectId, enabled: bool) -> Any:
        """Activa o pausa el agente que acciona los actuadores del cultivo según la IA."""
        return await user_api(client, ctx).set_automation(crop_id, enabled)

    @mcp.tool(name="get_crop_weather", title="Clima del cultivo", annotations=READ)
    async def get_crop_weather(ctx: Context, crop_id: ObjectId) -> Any:
        """Clima actual del lugar del cultivo (requiere que el cultivo tenga ubicación)."""
        return await user_api(client, ctx).crop_weather(crop_id)

    # ---------------------------------------------------------------- Lecturas

    @mcp.tool(name="get_latest_reading", title="Última lectura", annotations=READ)
    async def get_latest_reading(ctx: Context, crop_id: ObjectId) -> dict[str, Any]:
        """Última lectura: temperatura, humedad, luz, pH, TDS, presión y humedad del sustrato."""
        return await user_api(client, ctx).latest_reading(crop_id)

    @mcp.tool(name="get_readings_history", title="Historial de lecturas", annotations=READ)
    async def get_readings_history(
        ctx: Context,
        crop_id: ObjectId,
        from_time: Annotated[str, Field(description="Inicio RFC 3339, p. ej. 2026-10-31T00:00:00Z")] | None = None,
        to_time: Annotated[str, Field(description="Fin RFC 3339")] | None = None,
        limit: Annotated[int, Field(ge=1)] = 100,
    ) -> list[dict[str, Any]]:
        """Lecturas del cultivo en un rango de fechas, de la más reciente a la más antigua."""
        return await user_api(client, ctx).readings(crop_id, from_time, to_time, min(limit, settings.max_rows))

    @mcp.tool(name="get_readings_summary", title="Resumen de lecturas", annotations=READ)
    async def get_readings_summary(ctx: Context, crop_id: ObjectId, hours: Hours = 24) -> dict[str, Any]:
        """Mínimo, promedio y máximo de cada variable en las últimas horas."""
        return await user_api(client, ctx).readings_summary(crop_id, hours)

    @mcp.tool(name="record_reading", title="Registrar una lectura manual", annotations=WRITE)
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
        """Registra una medición tomada a mano (al menos una variable)."""
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
            raise ValueError("Indica al menos una variable medida")
        return await user_api(client, ctx).record_reading(crop_id, measures)

    # ---------------------------------------------------------------- Actuadores y comandos

    @mcp.tool(name="list_actuators", title="Actuadores del cultivo", annotations=READ)
    async def list_actuators(ctx: Context, crop_id: ObjectId) -> list[dict[str, Any]]:
        """Actuadores del cultivo (bomba, luz UV, ventilador, humidificador, dosificadores) y si están encendidos."""
        return await user_api(client, ctx).actuators(crop_id)

    @mcp.tool(name="send_actuator_command", title="Accionar un actuador", annotations=PHYSICAL)
    async def send_actuator_command(
        ctx: Context, crop_id: ObjectId, actuator_id: ObjectId, action: Action, duration_seconds: Duration | None = None
    ) -> dict[str, Any]:
        """Enciende o apaga un actuador por MQTT. Mueve hardware real en cultivos REAL: confirma antes."""
        return await user_api(client, ctx).send_command(crop_id, actuator_id, action, duration_seconds)

    @mcp.tool(name="send_bulk_command", title="Accionar varios cultivos", annotations=PHYSICAL)
    async def send_bulk_command(
        ctx: Context,
        crop_ids: Annotated[list[ObjectId], Field(min_length=1, max_length=50)],
        actuator_type: ActuatorType,
        action: Action,
        duration_seconds: Duration | None = None,
    ) -> dict[str, Any]:
        """Acciona el mismo tipo de actuador en varios cultivos; devuelve enviados, omitidos y fallidos."""
        return await user_api(client, ctx).send_bulk_command(crop_ids, actuator_type, action, duration_seconds)

    @mcp.tool(name="list_commands", title="Historial de comandos", annotations=READ)
    async def list_commands(
        ctx: Context, crop_id: ObjectId, limit: Annotated[int, Field(ge=1, le=200)] = 30
    ) -> list[dict[str, Any]]:
        """Comandos recientes del cultivo con su estado (PENDING, SENT, EXECUTED, FAILED, EXPIRED) y origen."""
        return await user_api(client, ctx).crop_commands(crop_id, limit)

    # ---------------------------------------------------------------- IA

    @mcp.tool(name="get_crop_insights", title="Diagnóstico de la IA", annotations=READ)
    async def get_crop_insights(ctx: Context, crop_id: ObjectId) -> dict[str, Any]:
        """Diagnóstico de SmartPot-AI: índice de salud 0-100, conclusiones, acciones sugeridas y pronóstico."""
        return await user_api(client, ctx).insights(crop_id)

    @mcp.tool(name="get_crop_profiles", title="Perfiles de cultivo", annotations=READ)
    async def get_crop_profiles() -> Any:
        """Rangos óptimos recomendados por tipo de cultivo."""
        return await client.crop_profiles()

    @mcp.tool(name="get_learning_status", title="Estado del aprendizaje", annotations=READ)
    async def get_learning_status(ctx: Context) -> Any:
        """Estado del aprendizaje continuo de la IA (muestras y versión de modelos)."""
        return await user_api(client, ctx).learning_status()

    # ---------------------------------------------------------------- Panel general

    @mcp.tool(name="get_overview", title="Panel general", annotations=READ)
    async def get_overview(ctx: Context) -> dict[str, Any]:
        """Resumen de la cuenta: cultivos, salud, dispositivos en línea, comandos y avisos."""
        return await user_api(client, ctx).overview()

    @mcp.tool(name="get_metric_series", title="Serie de una variable", annotations=READ)
    async def get_metric_series(ctx: Context, metric: Metric = "temperature", hours: Hours = 24) -> dict[str, Any]:
        """Promedios por intervalo de una variable para todos los cultivos (agregados de TimescaleDB)."""
        return await user_api(client, ctx).series(metric, hours)

    @mcp.tool(name="get_fleet", title="Análisis de la flota", annotations=READ)
    async def get_fleet(ctx: Context) -> Any:
        """Comparativa de todos los cultivos de la cuenta."""
        return await user_api(client, ctx).fleet()

    # ---------------------------------------------------------------- Notificaciones

    @mcp.tool(name="list_notifications", title="Notificaciones", annotations=READ)
    async def list_notifications(ctx: Context) -> Any:
        """Avisos de la cuenta (alertas de la IA, comandos, dispositivos)."""
        return await user_api(client, ctx).notifications()

    @mcp.tool(name="get_unread_count", title="Avisos sin leer", annotations=READ)
    async def get_unread_count(ctx: Context) -> Any:
        """Cantidad de notificaciones sin leer."""
        return await user_api(client, ctx).unread_count()

    @mcp.tool(name="mark_notification_read", title="Marcar aviso como leído", annotations=IDEMPOTENT)
    async def mark_notification_read(ctx: Context, notification_id: ObjectId) -> Any:
        """Marca una notificación como leída."""
        return await user_api(client, ctx).mark_read(notification_id)
