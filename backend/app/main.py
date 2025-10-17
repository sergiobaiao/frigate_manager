from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ConfigManager
from .database import init_db
from .routers import configuration, failures, hosts
from .tasks.scheduler import MonitorScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(title="Frigate Manager")

config_manager = ConfigManager()
scheduler = MonitorScheduler(config_manager)


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


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(hosts.router)
app.include_router(configuration.router)
app.include_router(failures.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
