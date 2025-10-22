from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers, MutableHeaders

from .config import ConfigManager
from .database import init_db
from .routers import configuration, failures, hosts
from .tasks.scheduler import MonitorScheduler
from .utils.paths import DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

logger = logging.getLogger("frigate_manager.api")

app = FastAPI(title="Frigate Manager")

config_manager = ConfigManager()
scheduler = MonitorScheduler(config_manager)
app.state.config_manager = config_manager
app.state.scheduler = scheduler


@app.middleware("http")
async def log_unhandled_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled exception during request %s %s", request.method, request.url.path
        )
        raise


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    scheduler.start()
    from .services.monitor import run_monitoring
    import asyncio

    asyncio.create_task(run_monitoring(config_manager))


@app.on_event("shutdown")
async def on_shutdown() -> None:
    scheduler.shutdown()


class PrivateNetworkCORSMiddleware(CORSMiddleware):
    """Extend FastAPI's CORS middleware to support private network requests."""

    @staticmethod
    def _should_allow_private_network(headers: Headers) -> bool:
        return headers.get("access-control-request-private-network", "").lower() == "true"

    def preflight_response(self, request_headers: Headers):  # type: ignore[override]
        response = super().preflight_response(request_headers)
        if self._should_allow_private_network(request_headers):
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response

    async def send(self, message, send, request_headers):  # type: ignore[override]
        if (
            message["type"] == "http.response.start"
            and self._should_allow_private_network(request_headers)
        ):
            headers = MutableHeaders(scope=message)
            headers["Access-Control-Allow-Private-Network"] = "true"
        await super().send(message, send=send, request_headers=request_headers)


app.add_middleware(
    PrivateNetworkCORSMiddleware,
    allow_origin_regex=r".*",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(hosts.router)
app.include_router(configuration.router)
app.include_router(failures.router)

app.mount("/media", StaticFiles(directory=str(DATA_DIR), check_dir=False), name="media")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
