# Vigil Deployment

Vigil is an open-source agentic SOC (DeepTempo, Apache 2.0). It routes all LLM traffic through
its Bifrost gateway. This deployment runs it entirely through Docker Compose.

## Installation

```bash
# LXC: Debian 12, features nesting=1,keyctl=1 (required to run Docker inside an unprivileged LXC)
cd /opt
git clone --recurse-submodules https://github.com/Vigil-SOC/vigil.git
cd vigil
git submodule update --init --recursive   # deeptempo-core, mcp-servers, mempalace
cp env.example .env
```

## Architecture decision: Docker only

Vigil ships both a native start script and a Docker Compose stack. Running both at once is not
supported: they compete for port 6987, and the native backend cannot resolve the `bifrost`
container name. The symptom is `address already in use :6987` alongside `bifrost_sync: false`
in the logs.

**Always start the stack this way:**

```bash
cd /opt/vigil/docker && docker compose up -d   # never ./start.sh
```

If the native mode is already running, stop it first with `cd /opt/vigil && ./shutdown_all.sh`
before switching to Docker.

## Stack containers

| Container | Port | Notes |
|---|---|---|
| deeptempo-backend | 6987 | FastAPI (uvicorn) |
| deeptempo-bifrost | 8080 | LLM gateway (maximhq/bifrost) |
| deeptempo-postgres | 5432 | Database |
| deeptempo-redis | 6379 | Cache / queues |
| deeptempo-llm-worker | - | LLM worker (its health check is a false negative, see [troubleshooting.md](troubleshooting.md)) |
| deeptempo-daemon | 8081, 9090-9091 | SOC daemon |
| frontend (Vite) | 6988 | Outside the Docker stack, started separately (see below) |

## Bifrost fixes: the critical integration point

File: `/opt/vigil/docker/bifrost/config.json`, section `providers.ollama`. Two fixes are
required for a remote Ollama instance on a private IP to work:

```python
# Python correction script (avoids manual JSON syntax errors)
python3 - <<'EOF'
import json
p = "/opt/vigil/docker/bifrost/config.json"
cfg = json.load(open(p))
oll = cfg["providers"]["ollama"]["keys"][0]
oll["models"] = ["*"]   # wildcard: accept any model exposed by Ollama
cfg["providers"]["ollama"].setdefault("network_config", {})["allow_private_network"] = True
json.dump(cfg, open(p, "w"), indent=2)
EOF
docker compose up -d --force-recreate bifrost
```

- **`allow_private_network: true`**: Bifrost >= v1.5.9 blocks RFC1918 private IPs by default as
  an anti-SSRF protection. Without this flag, requests to the local Ollama instance fail with
  `connection to private IP <ollama-ip> is not allowed` (HTTP 502). This was the root cause
  blocking all LLM calls.
- **`"models": ["*"]`**: the Ollama model allow-list baked into the default config does not
  include the Gemma models used here. Without the wildcard, requests fail with
  `no keys found that support model: gemma4:26b`.

See [config/bifrost-patch.py](../config/bifrost-patch.py) for the standalone version of this
script.

## Environment variables: hardcode in the Compose file

The Docker services do not have an `env_file` directive, so they do not read `.env` for their
internal variables. Every critical variable must be set directly in the `environment:` block of
the relevant service in `docker-compose.yml`, or it silently falls back to a broken default.

Backend service, `environment:` block:

```yaml
      - OLLAMA_URL=http://10.50.10.23:11434   # not localhost, not host.docker.internal
      - DEV_MODE=true                          # required, see below
      - BIFROST_URL=http://bifrost:8080        # service name, Docker network mode
```

- **`DEV_MODE=true`** is required because full authentication is still experimental. Without
  it, the backend crashes on startup with `RuntimeError: JWT_SECRET_KEY is required when
  DEV_MODE=false` and restarts in a loop.
- **Security implication**: `DEV_MODE=true` means there is no authentication at all. Vigil must
  therefore stay strictly on the LAN and never be exposed through a reverse proxy or a public
  domain.

## Permissions fix for `/app` (packaging bug)

`Dockerfile.backend` runs the container as the non-root user `vigil` (UID 999) but only grants
it ownership of `/app/data`. This causes cascading `PermissionError` exceptions on `/app/logs`,
`/app/data/investigations`, and `/app/.deeptempo`.

**Quick fix (host volumes and ownership):**

```bash
mkdir -p /opt/vigil/logs /opt/vigil/data
chmod -R 777 /opt/vigil/logs /opt/vigil/data
# mount these as volumes on the backend service in docker-compose.yml:
#   volumes:
#     - /opt/vigil/logs:/app/logs
#     - /opt/vigil/data:/app/data
docker exec -u root deeptempo-backend chown -R vigil:vigil /app
docker compose up -d --force-recreate backend
```

**Proper fix (in `Dockerfile.backend`, before `USER vigil`):**

```dockerfile
RUN mkdir -p /app/logs /app/data /app/.deeptempo && chown -R vigil:vigil /app
```

One line in the upstream Dockerfile resolves all three permission errors at once; the official
image simply does not provision non-root ownership across its full working directory.

## Frontend

The Vite frontend is not part of the Docker stack; it was previously started by `start.sh`. To
run it without bringing up the full native stack:

```bash
cd /opt/vigil/frontend
npm run dev -- --host 0.0.0.0 --port 6988
```

`--host 0.0.0.0` is required, otherwise Vite listens on `127.0.0.1` only and the UI is
unreachable from the LAN. Check the `Network:` line in Vite's startup output to confirm.

## Provider and model configuration in the UI

Settings -> AI Config -> Providers -> Ollama (`http://10.50.10.23:11434`).
Model Assignment -> Chat (Default) -> `my-ollama` / `gemma4:26b`.

- Bifrost routes with an `ollama/` provider prefix: `ollama/gemma4:26b`. Direct test call:
  `curl http://localhost:8080/v1/chat/completions -d '{"model":"ollama/gemma4:26b",...}'`.
- Model resync: `POST /api/llm/providers/refresh-models` (note the `llm/providers` path), or
  `/api/llm/providers/{id}/refresh-models`. Auto-sync runs every 5 minutes.
