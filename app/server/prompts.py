"""Plantillas de prompts de SmartPot (`@mcp.prompt()`)."""

from mcp.server.mcpserver import MCPServer


def register_prompts(mcp: MCPServer) -> None:
    @mcp.prompt(name="agronomic_diagnosis", title="Diagnóstico agronómico")
    def agronomic_diagnosis(crop_id: str, goal: str = "salud y crecimiento estables") -> str:
        """Evalúa un cultivo con su telemetría, el diagnóstico de la IA y el perfil de la especie."""
        return (
            f"Evalúa el cultivo {crop_id} con el objetivo: {goal}.\n"
            "1. get_crop: tipo, forma, lugar y si el automático está activo.\n"
            "2. get_latest_reading y get_readings_summary (24 h): valores actuales y tendencia.\n"
            "3. get_crop_insights: índice de salud, conclusiones y acciones sugeridas por la IA.\n"
            "4. get_crop_profiles: compara con los rangos óptimos del tipo de cultivo.\n"
            "5. Propón acciones concretas. No accionas actuadores sin confirmación explícita del usuario."
        )

    @mcp.prompt(name="emergency_triage", title="Atención de una alerta")
    def emergency_triage(crop_id: str, alert: str) -> str:
        """Guía para atender una alerta crítica (calor, pH fuera de rango, sustrato seco)."""
        return (
            f"Alerta en el cultivo {crop_id}: {alert}.\n"
            "1. get_latest_reading para medir la desviación.\n"
            "2. list_actuators y list_commands para ver qué está encendido o en curso.\n"
            "3. Propón el comando mínimo (actuador, acción y duración) y explica el motivo agronómico.\n"
            "4. Solo usa send_actuator_command tras la confirmación del usuario; luego verifica con list_commands."
        )

    @mcp.prompt(name="fleet_daily_summary", title="Resumen diario de la flota")
    def fleet_daily_summary(hours: int = 24) -> str:
        """Informe breve del estado de todos los cultivos."""
        return (
            "Prepara el resumen diario de la cuenta:\n"
            "1. get_overview y get_fleet.\n"
            f"2. get_metric_series de temperatura, humedad y pH en las últimas {hours} h.\n"
            "3. list_notifications para los avisos pendientes.\n"
            "4. Agrupa: cultivos sanos, cultivos en riesgo y tareas sugeridas para hoy."
        )
