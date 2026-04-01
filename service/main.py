"""
Agentify Container - Main FastAPI Application

This is the entry point. An AI agent building on this template should:
1. Add domain-specific routes in service/routers/api.py
2. Register MCP tools in mcp/sse_server.py
3. Update config/service.example.json with service-specific settings
4. Update integrations/ (Claude Code skill, OpenClaw plugin, Open WebUI tool)
"""

import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from service.config import get_config
from service.routers import health, api, containers as containers_router

import hmac
from starlette.middleware.base import BaseHTTPMiddleware


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Enforces API key auth when API_KEY is set in .env."""

    SKIP_PATHS = {"/health", "/ready", "/info", "/docs", "/redoc", "/openapi.json"}

    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request, call_next):
        if request.url.path in self.SKIP_PATHS or request.url.path.startswith("/docs"):
            return await call_next(request)
        provided_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if not provided_key or not hmac.compare_digest(provided_key, self.api_key):
            from starlette.responses import JSONResponse
            return JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)
        return await call_next(request)


def _setup_logging(config):
    """Configure logging based on config."""
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    if config.log_format == "json":
        fmt = '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
    else:
        fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout, force=True)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle."""
    config = get_config()
    _setup_logging(config)
    logger.info(f"Starting {config.name} v{config.version}")

    # --- STARTUP ---
    container_manager = None
    json_path = Path(config.config_dir) / "service.json"
    if json_path.exists():
        try:
            with open(json_path) as f:
                config_data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {json_path}: {e}")
            config_data = {}

        if config_data.get("containers", {}).get("definitions"):
            from service.containers.manager import ContainerManager, load_container_definitions
            try:
                definitions, defaults = load_container_definitions(config_data)
                container_manager = ContainerManager(definitions, defaults)
                app.state.container_manager = container_manager
                await container_manager.start_background_tasks()
                logger.info(f"Container manager: {len(definitions)} containers defined")
            except Exception as e:
                logger.error(f"Container manager init failed: {e}")

    # TODO: Initialize your service resources here
    #   app.state.my_resource = await create_resource()

    # Mount MCP server if enabled
    if config.mcp_enabled:
        try:
            import importlib.util
            _sse_path = Path(__file__).resolve().parent.parent / "mcp" / "sse_server.py"
            _spec = importlib.util.spec_from_file_location("sse_server", _sse_path)
            _mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            _mod.setup_mcp_server(app)
            logger.info(f"MCP SSE at {config.mcp_path_prefix}/sse")
        except Exception as e:
            logger.info(f"MCP SSE server not available: {e}")

    yield

    # --- SHUTDOWN ---
    if container_manager:
        await container_manager.shutdown()
    logger.info(f"Shutting down {config.name}")


def create_app() -> FastAPI:
    config = get_config()

    app = FastAPI(
        title=config.name,
        version=config.version,
        description=config.description,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    origins = config.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=("*" not in origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API key auth — only enforced when API_KEY is set in .env
    if config.api_key:
        app.add_middleware(APIKeyMiddleware, api_key=config.api_key)
        logger.info("API key auth enabled")

    app.include_router(health.router)
    app.include_router(api.router, prefix="/api/v1")
    app.include_router(containers_router.router)

    # Redirect root to dashboard or docs
    from fastapi.responses import RedirectResponse

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/docs")

    return app


app = create_app()
