# SmartPot-MCP

Servidor de **Model Context Protocol (MCP)** de SmartPot: permite que un asistente de IA compatible con MCP consulte
los cultivos, lea la telemetría, pida el diagnóstico de la IA y, si la persona lo autoriza, accione los actuadores,
siempre a nombre de la cuenta de quien se conecta.

---

## Conexiones separadas por cuenta

El servidor **no tiene cuenta propia**. Cada persona crea en la PWA, en **Perfil › Conexiones**, un token de conexión
(`spt_…`) con un alcance:

| Alcance       | Qué permite                                                                  |
|---------------|------------------------------------------------------------------------------|
| Solo lectura  | Consultar cultivos, lecturas, diagnósticos, panel general y avisos           |
| Control       | Además, crear, editar y borrar cultivos, accionar actuadores y marcar avisos |

El cliente MCP envía ese token en cada petición (`Authorization: Bearer spt_…`) y el servidor lo reenvía a
SmartPot-API, que decide: solo ve los cultivos de esa cuenta y aplica su alcance. Ninguna conexión puede cambiar la
contraseña, administrar otras conexiones, configurar canales de aviso ni ver las credenciales de un dispositivo.
Revocar la conexión en la PWA la corta al instante; la API guarda solo el SHA-256 del token y registra su último uso.

El transporte HTTP no guarda estado entre peticiones: cada una se atiende de forma aislada con el token que trae.

---

## Despliegue en un comando

La imagen es pública: `ghcr.io/smartpottech/smartpot-mcp`. Viene incluida en la demo beta, que se levanta sin
descargar el código:

```bash
curl -fsSL https://raw.githubusercontent.com/SmartPotTech/.github/main/docker/demo-beta/compose.yaml | docker compose -f - up -d --wait
```

El servidor MCP queda en `http://localhost:8002/mcp` (salud en `http://localhost:8002/health`). Ingresa a la PWA en
http://localhost:5173 con `demo@smartpot.app` / `SmartPot2026`, crea una conexión en **Perfil › Conexiones** y copia
la configuración que muestra.

Solo este servicio, apuntando a una API existente:

```bash
docker run -d --name smartpot-mcp -p 127.0.0.1:8002:8002 --read-only --cap-drop ALL \
  -e SMARTPOT_API_URL=http://host.docker.internal:8091 \
  ghcr.io/smartpottech/smartpot-mcp:latest
```

---

## Configurar el cliente MCP

### HTTP (recomendado)

```json
{
  "mcpServers": {
    "smartpot": {
      "type": "http",
      "url": "http://localhost:8002/mcp",
      "headers": { "Authorization": "Bearer spt_…" }
    }
  }
}
```

### stdio (cliente local)

```json
{
  "mcpServers": {
    "smartpot": {
      "command": "uv",
      "args": ["--directory", "<carpeta de SmartPot-MCP>", "run", "python", "-m", "app.main"],
      "env": { "SMARTPOT_API_URL": "http://localhost:8091", "SMARTPOT_API_TOKEN": "spt_…" }
    }
  }
}
```

---

## Capacidades

### Herramientas

| Grupo          | Herramientas                                                                                        |
|----------------|-----------------------------------------------------------------------------------------------------|
| Cuenta         | `get_account`                                                                                       |
| Cultivos       | `list_crops`, `get_crop`, `create_crop`, `update_crop`, `delete_crop`, `set_crop_automation`, `get_crop_weather` |
| Lecturas       | `get_latest_reading`, `get_readings_history`, `get_readings_summary`, `record_reading`              |
| Actuadores     | `list_actuators`, `send_actuator_command`, `send_bulk_command`, `list_commands`                     |
| IA             | `get_crop_insights`, `get_crop_profiles`, `get_learning_status`                                     |
| Panel general  | `get_overview`, `get_metric_series`, `get_fleet`                                                    |
| Avisos         | `list_notifications`, `get_unread_count`, `mark_notification_read`                                  |

Cada herramienta declara si es de solo lectura, idempotente o destructiva, para que el cliente pida confirmación antes
de mover hardware o borrar datos. Al crear un cultivo real, las credenciales del dispositivo nunca se devuelven por MCP.

### Recursos

- `smartpot://crops/{crop_id}`, `smartpot://crops/{crop_id}/latest` y `smartpot://crops/{crop_id}/insights`.
- `smartpot://profiles` y `smartpot://health` (públicos).

### Prompts

`agronomic_diagnosis`, `emergency_triage` y `fleet_daily_summary`.

---

## Desarrollo

Requiere [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen
uv run python -m app.main                                  # stdio (usa SMARTPOT_API_TOKEN)
TRANSPORT=streamable-http uv run python -m app.main        # HTTP en el puerto 8002
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

Las pruebas simulan la API y comprueban que cada petición llega con el token de quien llama, que dos cuentas no se
mezclan, que sin token o con un JWT de sesión no se llega a la API, que una conexión de solo lectura no acciona y que
las credenciales del dispositivo no se exponen.

## Seguridad del contenedor

Usuario sin privilegios (`1000:1000`), sistema de archivos de solo lectura, sin capacidades y protección contra DNS
rebinding (`MCP_ALLOWED_HOSTS` y `MCP_ALLOWED_ORIGINS`).

## Licencia

MIT.
