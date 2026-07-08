# Troubleshooting Reference

Issues encountered while integrating Wazuh, Vigil, and Ollama into a single sovereign chain,
and how each was resolved. Most of these come down to a small number of upstream assumptions
(cloud-only LLM providers, root-owned working directories, a single deployment mode) that do
not hold in a private, self-hosted, non-root setup.

| Symptom | Cause | Fix |
|---|---|---|
| `address already in use :6987` | Native start script and Docker Compose running at the same time | Run only one mode (Docker); stop the native mode with `./shutdown_all.sh` first |
| Frontend unreachable ("connection failed") | Vite dev server bound to `127.0.0.1` | Start with `--host 0.0.0.0` |
| `no keys found that support model: gemma4:26b` | Ollama model allow-list hardcoded in Bifrost's config | Set `"models": ["*"]` in `bifrost/config.json` |
| `connection to private IP ... is not allowed` (HTTP 502) | Bifrost's anti-SSRF filter blocks RFC1918 addresses by default | Set `allow_private_network: true` for the Ollama provider |
| `bifrost_sync: false` | `OLLAMA_URL` pointed at `localhost` instead of the LXC's LAN IP | Set the real LAN address, e.g. `http://10.50.10.23:11434` |
| `RuntimeError: JWT_SECRET_KEY is required when DEV_MODE=false` | `DEV_MODE` not propagated to the backend container | Hardcode `DEV_MODE=true` in the Compose `environment:` block |
| `could not translate host name "postgres"` | Docker network not recreated after a config change | `docker compose down && docker compose up -d` |
| `PermissionError` on `/app/logs`, `/app/data/investigations`, `/app/.deeptempo` | Non-root container user without ownership of its own working directory | `chown -R vigil:vigil /app`, or fix the Dockerfile (see [deployment-vigil.md](deployment-vigil.md)) |
| IP conflict between Wazuh and an unrelated homelab LXC | Both assigned the same address | Move Wazuh to a free address and re-enroll the Windows agent |
| Investigations fail at iteration 0, missing `log.jsonl` | Upstream Vigil orchestrator bug: the investigation log directory is not fully initialized | Not resolved on this deployment; requires an upstream patch. Confirmed not a permissions or config issue (directories are writable, ownership correct). |

## Known, accepted limitations

- **`deeptempo-llm-worker` reports `unhealthy`**: the health check tests an internal port from
  inside the container in a way that produces a false negative; the worker itself functions
  correctly and this was left as-is.
- **Frontend runs outside the Docker stack**: started manually with `npm run dev`, not yet
  containerized (see the [roadmap](../README.md#7-roadmap)).
