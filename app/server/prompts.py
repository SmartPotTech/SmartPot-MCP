"""SmartPot prompt templates (`@mcp.prompt()`)."""

from mcp.server.mcpserver import MCPServer


def register_prompts(mcp: MCPServer) -> None:
    @mcp.prompt(name="agronomic_diagnosis", title="Agronomic diagnosis")
    def agronomic_diagnosis(crop_id: str, goal: str = "stable health and growth") -> str:
        """Evaluates a crop using its telemetry, AI diagnosis, and species profile."""
        return (
            f"Evaluate crop {crop_id} with goal: {goal}.\n"
            "1. get_crop: type, form, placement, and whether automation is active.\n"
            "2. get_latest_reading and get_readings_summary (24 h): current values and trend.\n"
            "3. get_crop_insights: health index, conclusions, and AI-suggested actions.\n"
            "4. get_crop_profiles: compare against the optimal ranges for the crop species.\n"
            "5. Propose concrete actions. Do not trigger actuators without explicit user confirmation."
        )

    @mcp.prompt(name="emergency_triage", title="Alert triage")
    def emergency_triage(crop_id: str, alert: str) -> str:
        """Guide for triaging a critical alert (heat, out-of-range pH, dry substrate)."""
        return (
            f"Alert on crop {crop_id}: {alert}.\n"
            "1. get_latest_reading to measure the deviation.\n"
            "2. list_actuators and list_commands to inspect what is active or in progress.\n"
            "3. Propose the minimal command (actuator, action, and duration) and explain the agronomic reason.\n"
            "4. Only call send_actuator_command after user confirmation; then verify with list_commands."
        )

    @mcp.prompt(name="fleet_daily_summary", title="Daily fleet summary")
    def fleet_daily_summary(hours: int = 24) -> str:
        """Concise status report across all crops."""
        return (
            "Prepare the daily account summary:\n"
            "1. get_overview and get_fleet.\n"
            f"2. get_metric_series for temperature, humidity, and pH over the last {hours} h.\n"
            "3. list_notifications for pending alerts.\n"
            "4. Group into: healthy crops, at-risk crops, and suggested tasks for today."
        )
