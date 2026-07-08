# Architecture

All addressing below is anonymized: real LAN prefixes were replaced with a generic `10.50.x.x`
range, and the monitored Windows workstation's real hostname was replaced with
`WORKSTATION-01`. Container roles, port numbers, and the overall segmentation logic are kept
identical to the original deployment, since that structure is what matters technically.

## Network map

| IP (anonymized) | Host | Role |
|---|---|---|
| `10.50.10.20` | Wazuh (LXC) | SIEM: Manager + Indexer + Dashboard. Moved here from `10.50.10.25` after an IP conflict, see below. |
| `10.50.10.21` | LXC | Unrelated homelab service (agents R&D) |
| `10.50.10.22` | LXC | Unrelated homelab service (nutrition tracker) |
| `10.50.10.23` | Ollama (LXC) | LLM inference, Vulkan iGPU backend |
| `10.50.10.24` | Vigil (LXC) | Agentic SOC, Docker Compose stack |
| `10.50.10.25` | Docker (LXC) | General homelab (media/file services) |
| `10.50.11.50` | Windows PC (`WORKSTATION-01`) | Monitored endpoint: Wazuh agent + Sysmon |

### IP conflict encountered

Wazuh was initially deployed on `10.50.10.25`, which was already in use by the general-purpose
Docker homelab LXC. This was resolved by moving Wazuh to `10.50.10.20` and keeping the homelab
LXC on `10.50.10.25`:

```bash
# on the Proxmox host
pct set 250 --net0 name=eth0,bridge=vmbr0,ip=10.50.10.20/24,gw=10.50.10.1
pct reboot 250
```

The Windows agent was then re-enrolled against the new manager address. The Wazuh-to-Vigil
bridge was unaffected, since it targets Vigil's fixed address directly.

## Ports

| Service | Port(s) | Notes |
|---|---|---|
| Ollama | `11434` | LLM inference API |
| Vigil backend | `6987` | FastAPI (uvicorn) |
| Vigil frontend | `6988` | Vite dev server, outside the Docker stack |
| Bifrost gateway | `8080` | LLM routing |
| Vigil daemon | `8081`, `9090`-`9091` | SOC daemon |
| Wazuh dashboard | `443` (HTTPS) | Self-signed certificate |
| Wazuh agent <-> manager | `1514` | Event forwarding |
| Wazuh enrollment | `1515` | Agent registration |
| Wazuh indexer | `9200` | OpenSearch |

## Data flow

1. An attack simulation (PowerShell, dropper) runs on `WORKSTATION-01`.
2. Sysmon captures process, command-line, and network telemetry; the Wazuh agent forwards it to
   the Wazuh Manager.
3. Wazuh evaluates the event against its rule set. Alerts at level 12 or above trigger the
   `custom-vigil.py` integration script through `integratord`.
4. The bridge script converts the Wazuh alert into a Vigil finding (severity, MITRE mapping,
   enriched entity context) and posts it to Vigil's ingestion API.
5. Vigil's agents pick up the finding and, through the Bifrost gateway, query the local Ollama
   instance (`gemma4:26b`) to qualify it.
6. The qualified finding, including the AI's analysis, is available in the Vigil dashboard.

See [bridge.md](bridge.md) for the bridge implementation and [deployment-wazuh.md](deployment-wazuh.md) /
[deployment-vigil.md](deployment-vigil.md) for the full deployment runbooks.
