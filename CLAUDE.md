# Agentify Container Template

AI agent-friendly Docker service template with on-demand sub-container orchestration. The orchestrator manages Docker containers via the Docker SDK - starting them on first request, routing traffic, tracking GPU allocation, and auto-stopping after idle.

## Quick Start

```bash
bash setup.sh                     # Copy config templates
# Edit .env (project name, ports)
# Copy a config/examples/*.json to config/service.json
docker compose up -d --build
bash scripts/test-endpoints.sh
```

## Project Structure

```
.
├── .env.example                         # Deployment config (ports, resources)
├── Dockerfile                           # Orchestrator container (Python 3.12)
├── docker-compose.yml                   # Main compose (mounts docker.sock)
├── docker-compose.dev.yml               # Dev override (hot-reload, source mount)
├── service/
│   ├── main.py                          # App entry + container manager init + logging
│   ├── config.py                        # Config loader (env > json > defaults)
│   ├── requirements.txt
│   ├── containers/
│   │   ├── manager.py                   # ContainerManager: start/stop/health/idle/restart
│   │   ├── gpu.py                       # GPUAllocator: device tracking, fractions, exclusive
│   │   ├── models.py                    # ContainerDefinition, ContainerState (Pydantic)
│   │   └── proxy.py                     # Streaming HTTP reverse proxy (SSE/chunked)
│   └── routers/
│       ├── health.py                    # /health, /ready, /info (discovery)
│       ├── api.py                       # YOUR ENDPOINTS GO HERE
│       └── containers.py               # /api/v1/containers/*, /route/{name}/*
├── mcp/
│   ├── sse_server.py                    # MCP SSE server (container mgmt tools built-in)
│   └── stdio/
│       ├── server.js                    # Host-side MCP (mirrors all tools)
│       └── package.json
├── integrations/
│   ├── claude-code/SKILL.md             # Skill: all tools + usage + install
│   ├── openclaw/{plugin.json, index.ts} # Plugin: tools + auto-hooks
│   └── open-webui/{tool.py, prompt.md}  # Tool + system prompt addition
├── config/
│   ├── service.example.json             # Minimal config template
│   ├── examples/
│   │   ├── minimal-single-llm.json      # Simplest: 1 container
│   │   ├── llama-cpp-router.json        # 3x llama.cpp (embed+qwen+glm4)
│   │   └── openclaw-full-stack.json     # Full stack with shared containers
│   └── workspace/
│       ├── AGENTS.md                    # File map + endpoint reference
│       └── IDENTITY.md                  # Service identity
└── scripts/
    ├── add-service.sh                   # Add sub-service (scaffold or git submodule)
    ├── compose-up.sh                    # Start with all sub-services from .env
    └── test-endpoints.sh                # Test all endpoints
```

## Container Configuration

All containers are defined in `config/service.json` under the `containers` key. The `defaults` block sets shared defaults; each `definitions` entry overrides only what it needs.

### Minimal config:
```json
{
  "containers": {
    "defaults": {
      "image": "ghcr.io/ggerganov/llama.cpp:server-cuda",
      "internal_port": 8080,
      "idle_timeout_seconds": 300,
      "gpu": { "device_ids": ["0"] },
      "volumes": { "llm-models": "/models" }
    },
    "definitions": {
      "llm": { "command": ["--model", "/models/model.gguf", "--port", "8080", "--gpu-layers", "99"] }
    }
  }
}
```

### Container sharing:
```json
"openmemory-llm": { "shared_with": "inference-llm", "group": "openmemory" }
```
This means: don't start a new container, use `inference-llm`'s URL.

### GPU scheduling:
```json
"gpu": { "device_ids": ["0"], "memory_fraction": 0.6, "exclusive": false }
```
The manager tracks fractions per device and refuses starts that would exceed 100%.

### Key fields:
| Field | Default | Purpose |
|-------|---------|---------|
| `image` | (required) | Docker image |
| `internal_port` | 8080 | Port process listens on |
| `command` | [] | Override container CMD |
| `volumes` | {} | Named volume -> mount path |
| `environment` | {} | Env vars for the container |
| `gpu.device_ids` | [] | NVIDIA GPU devices |
| `gpu.memory_fraction` | 1.0 | Scheduling fraction (0-1) |
| `gpu.exclusive` | false | Lock GPU to this container |
| `idle_timeout_seconds` | 300 | Auto-stop after idle (0=never) |
| `auto_start` | false | Start on orchestrator boot |
| `group` | "" | Logical group name |
| `shared_with` | "" | Use another container's URL |
| `health_check.endpoint` | "/health" | Readiness poll path |

## Building on This Template

When asked to build a service (e.g., "build a llama.cpp router"):

### 1. Define containers
Edit `config/service.example.json`. See `config/examples/` for patterns.

### 2. Add API endpoints
Edit `service/routers/api.py`. Access containers via `request.app.state.container_manager`.

### 3. Register MCP tools
Edit `mcp/sse_server.py` (SSE, in-container) and `mcp/stdio/server.js` (stdio, host-side). Container management tools (`list_containers`, `start_container`, etc.) are already built-in.

### 4. Update integrations
- `integrations/claude-code/SKILL.md` - Tool list and usage
- `integrations/openclaw/index.ts` - Plugin tools + event hooks
- `integrations/open-webui/tool.py` - Chat UI tools

### 5. Add dependencies
- Python: `service/requirements.txt`
- System: `Dockerfile` apt-get line
- Node: `mcp/stdio/package.json`

### 6. Test
```bash
docker compose up -d --build && bash scripts/test-endpoints.sh
```

## Endpoints

| Path | Method | Purpose |
|------|--------|---------|
| `/health` | GET | Health check |
| `/ready` | GET | Readiness with component status |
| `/info` | GET | Full service discovery |
| `/docs` | GET | OpenAPI documentation |
| `/api/v1/` | * | Your service endpoints |
| `/api/v1/containers` | GET | List all containers |
| `/api/v1/containers/{name}/start` | POST | Start container |
| `/api/v1/containers/{name}/stop` | POST | Stop container |
| `/api/v1/containers/{name}/logs` | GET | Container logs |
| `/api/v1/gpu` | GET | GPU allocation |
| `/route/{name}/{path}` | * | Proxy to container (auto-starts) |
| `/mcp/sse` | GET | MCP SSE endpoint |

## Config Precedence

```
COMPOSE_PROJECT_NAME in .env  ->  compose_project_name in service.json  ->  "agentify"
SERVICE_PORT in .env           ->  port in service.json                  ->  8800
(env vars always win)
```

`.env` = deployment (ports, resources, credentials, project name)
`service.json` = service definition (containers, custom settings)

## Conventions

- Persistent data in `/data` (named volume) or per-container named volumes
- Sub-containers accessed by Docker network hostname, not localhost
- Docker socket mounted for container management (see Security Note in README)
- Internal port always 8800 (change external mapping in .env)
