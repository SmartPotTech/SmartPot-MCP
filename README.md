# SmartPot-MCP

[English](#english) | [Español](#español)

---

<a id="english"></a>

## English

SmartPot **Model Context Protocol (MCP)** server: enables MCP-compatible AI assistants to inspect crops, read telemetry, request AI diagnostics, and—when authorized by the user—operate actuators, always on behalf of the connected account.

---

### Per-Account Isolated Connections

The server **does not have its own account**. Each user creates a connection token (`spt_…`) in the PWA under **Profile › Connections** with a defined scope:

| Scope     | Capabilities                                                                       |
|-----------|------------------------------------------------------------------------------------|
| Read-only | Query crops, readings, diagnostics, overview dashboard, and notifications          |
| Control   | Additionally create, edit, and delete crops, trigger actuators, and mark alerts    |

The MCP client sends that token on every request (`Authorization: Bearer spt_…`) and the server forwards it to `SmartPot-API`, which enforces isolation: it only sees that account's crops and applies its scope. No connection can change the password, manage other connections, configure notification channels, or view device credentials. Revoking a connection in the PWA takes effect within the 30-second positive/negative validation cache; the API stores only the SHA-256 digest of the token and records its last use. The MCP edge calls `GET /api/v1/users/me` with the connection token, caches the verdict by SHA-256 for 30 seconds (`MCP_TOKEN_CACHE_SECONDS`), and rejects fake or revoked tokens with `401` on every route, including `tools/list`.

The HTTP transport is stateless across requests: each request is served in isolation using the token it carries.

---

### One-Command Deployment

The image is public: `ghcr.io/smartpottech/smartpot-mcp`. It is included in the demo environment, which starts without cloning the code:

```bash
curl -fsSL https://raw.githubusercontent.com/SmartPotTech/.github/main/docker/demo/compose.yaml | docker compose -f - up -d --wait
```

In the local demo, the MCP server listens at `http://localhost:8002/mcp` (health check at `http://localhost:8002/health`). In production, it is deployed at `https://mcp.smartpot.app/mcp` (internal port 8092). Sign in to the PWA at http://localhost:5173 with `demo@smartpot.app` / `SmartPot2026`, create a connection in **Profile › Connections**, and copy the displayed configuration.

To run only this service pointing to an existing API:

```bash
docker run -d --name smartpot-mcp -p 127.0.0.1:8002:8002 --read-only --cap-drop ALL \
  -e SMARTPOT_API_URL=http://host.docker.internal:8091 \
  ghcr.io/smartpottech/smartpot-mcp:latest
```

---

### Configuring the MCP Client

#### HTTP (recommended)

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

#### stdio (local client)

```json
{
  "mcpServers": {
    "smartpot": {
      "command": "uv",
      "args": ["--directory", "<SmartPot-MCP directory>", "run", "python", "-m", "app.main"],
      "env": { "SMARTPOT_API_URL": "http://localhost:8091", "SMARTPOT_API_TOKEN": "spt_…" }
    }
  }
}
```

---

### Capabilities

#### Tools

| Group      | Tools                                                                                                            |
|------------|------------------------------------------------------------------------------------------------------------------|
| Account    | `get_account`                                                                                                    |
| Crops      | `list_crops`, `get_crop`, `create_crop`, `update_crop`, `delete_crop`, `set_crop_automation`, `get_crop_weather` |
| Readings   | `get_latest_reading`, `get_readings_history`, `get_readings_summary`, `record_reading`                           |
| Actuators  | `list_actuators`, `send_actuator_command`, `send_bulk_command`, `list_commands`                                  |
| AI         | `get_crop_insights`, `get_crop_profiles`, `get_learning_status`                                                  |
| Overview   | `get_overview`, `get_metric_series`, `get_fleet`                                                                 |
| Alerts     | `list_notifications`, `get_unread_count`, `mark_notification_read`                                               |

Each tool declares whether it is read-only, idempotent, or destructive so the client prompts for confirmation before operating hardware or deleting data. When creating a physical crop, device credentials are never returned over MCP.

#### Resources

- `smartpot://crops/{crop_id}`, `smartpot://crops/{crop_id}/latest`, and `smartpot://crops/{crop_id}/insights`.
- `smartpot://profiles` and `smartpot://health` (public).

#### Prompts

`agronomic_diagnosis`, `emergency_triage`, and `fleet_daily_summary`.

---

### Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen
uv run python -m app.main                                  # stdio (uses SMARTPOT_API_TOKEN)
TRANSPORT=streamable-http uv run python -m app.main        # HTTP on port 8002
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

Tests mock the API and verify that each request arrives with the caller's token, that two accounts never mix, that missing tokens or session JWTs never reach the API, that a fabricated well-formed `spt_` token is rejected on `tools/list`, that the 30-second cache avoids repeated validation calls, that read-only connections cannot trigger actuators, that deceptive Host/Origin values are rejected, and that device credentials are never exposed.

### Container Security

Unprivileged user (`1000:1000`), read-only filesystem, all capabilities dropped, strict `Host`/`Origin` parsing (`MCP_ALLOWED_HOSTS` and `MCP_ALLOWED_ORIGINS`; lowercase, exact authority, ports `1..65535`, IPv6), and an explicit CORS allowlist instead of `*`. `/health` stays public for probes.

### Interactive Diagrams

The [interactive diagrams](docs/diagrams/interactive/README.md#english) follow one tool call from the Host/Origin check to SmartPot-API, in English and Spanish, with links to the exact source lines.

### License

MIT.

---

<a id="español"></a>

## Español

Servidor de **Model Context Protocol (MCP)** de SmartPot: permite que un asistente de IA compatible con MCP consulte
los cultivos, lea la telemetría, pida el diagnóstico de la IA y, si la persona lo autoriza, accione los actuadores,
siempre a nombre de la cuenta de quien se conecta.

---

### Conexiones separadas por cuenta

El servidor **no tiene cuenta propia**. Cada persona crea en la PWA, en **Perfil › Conexiones**, un token de conexión
(`spt_…`) con un alcance:

| Alcance       | Qué permite                                                                  |
|---------------|------------------------------------------------------------------------------|
| Solo lectura  | Consultar cultivos, lecturas, diagnósticos, panel general y avisos           |
| Control       | Además, crear, editar y borrar cultivos, accionar actuadores y marcar avisos |

El cliente MCP envía ese token en cada petición (`Authorization: Bearer spt_…`) y el servidor lo reenvía a
SmartPot-API, que decide: solo ve los cultivos de esa cuenta y aplica su alcance. Ninguna conexión puede cambiar la
contraseña, administrar otras conexiones, configurar canales de aviso ni ver las credenciales de un dispositivo.
Revocar la conexión en la PWA surte efecto dentro de la caché de validación de 30 segundos (positiva o negativa); la API guarda solo el SHA-256 del token y registra su último uso. El borde MCP llama `GET /api/v1/users/me` con el token de conexión, cachea el veredicto por SHA-256 durante 30 segundos (`MCP_TOKEN_CACHE_SECONDS`) y rechaza tokens falsos o revocados con `401` en todas las rutas, incluido `tools/list`.

El transporte HTTP no guarda estado entre peticiones: cada una se atiende de forma aislada con el token que trae.

---

### Despliegue en un comando

La imagen es pública: `ghcr.io/smartpottech/smartpot-mcp`. Viene incluida en la demo local y en producción, y se levanta sin
descargar el código:

```bash
curl -fsSL https://raw.githubusercontent.com/SmartPotTech/.github/main/docker/demo/compose.yaml | docker compose -f - up -d --wait
```

En la demo local, el servidor MCP queda en `http://localhost:8002/mcp` (salud en `http://localhost:8002/health`). En producción, se despliega en `https://mcp.smartpot.app/mcp` (puerto interno 8092). Ingresa a la PWA en
http://localhost:5173 con `demo@smartpot.app` / `SmartPot2026`, crea una conexión en **Perfil › Conexiones** y copia
la configuración que muestra.

Solo este servicio, apuntando a una API existente:

```bash
docker run -d --name smartpot-mcp -p 127.0.0.1:8002:8002 --read-only --cap-drop ALL \
  -e SMARTPOT_API_URL=http://host.docker.internal:8091 \
  ghcr.io/smartpottech/smartpot-mcp:latest
```

---

### Configurar el cliente MCP

#### HTTP (recomendado)

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

#### stdio (cliente local)

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

### Capacidades

#### Herramientas

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

#### Recursos

- `smartpot://crops/{crop_id}`, `smartpot://crops/{crop_id}/latest` y `smartpot://crops/{crop_id}/insights`.
- `smartpot://profiles` y `smartpot://health` (públicos).

#### Prompts

`agronomic_diagnosis`, `emergency_triage` y `fleet_daily_summary`.

---

### Desarrollo

Requiere [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen
uv run python -m app.main                                  # stdio (usa SMARTPOT_API_TOKEN)
TRANSPORT=streamable-http uv run python -m app.main        # HTTP en el puerto 8002
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

Las pruebas simulan la API y comprueban que cada petición llega con el token de quien llama, que dos cuentas no se
mezclan, que sin token o con un JWT de sesión no se llega a la API, que un token `spt_` bien formado pero falso se
rechaza en `tools/list`, que la caché de 30 segundos evita validaciones repetidas, que una conexión de solo lectura no
acciona, que valores engañosos de Host/Origin se rechazan y que
las credenciales del dispositivo no se exponen.

### Seguridad del contenedor

Usuario sin privilegios (`1000:1000`), sistema de archivos de solo lectura, sin capacidades, análisis estricto de
`Host`/`Origin` (`MCP_ALLOWED_HOSTS` y `MCP_ALLOWED_ORIGINS`: minúsculas, autoridad exacta, puertos `1..65535`, IPv6)
y lista CORS explícita en vez de `*`. `/health` sigue siendo público para los probes.

### Diagramas interactivos

Los [diagramas interactivos](docs/diagrams/interactive/README.md#español) siguen una llamada a una herramienta desde la validación de Host/Origin hasta SmartPot-API, en español e inglés, con enlaces a las líneas exactas del código.

### Licencia

MIT.
