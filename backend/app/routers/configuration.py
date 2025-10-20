from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException
from playwright.async_api import async_playwright

from ..config import ConfigManager
from ..schemas.configuration import (
    ConfigRead,
    ConfigUpdate,
    ScreenshotTestRequest,
    ScreenshotTestResponse,
)

router = APIRouter(prefix="/config", tags=["config"])


def get_manager() -> ConfigManager:
    from ..main import config_manager

    return config_manager


def get_scheduler():
    from ..main import scheduler

    return scheduler


@router.get("", response_model=ConfigRead)
def read_config(manager: ConfigManager = Depends(get_manager)) -> ConfigRead:
    config = manager.get()
    return ConfigRead(**config.dict(by_alias=True))


@router.put("", response_model=ConfigRead)
def update_config(
    payload: ConfigUpdate,
    manager: ConfigManager = Depends(get_manager),
    monitor_scheduler=Depends(get_scheduler),
) -> ConfigRead:
    config = manager.update(payload.dict(exclude_unset=True))
    monitor_scheduler.reload()
    return ConfigRead(**config.dict(by_alias=True))


@router.post("/test-screenshot", response_model=ScreenshotTestResponse)
async def capture_test_screenshot(payload: ScreenshotTestRequest) -> ScreenshotTestResponse:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(payload.url, wait_until="networkidle", timeout=60000)
            screenshot_bytes = await page.screenshot(full_page=True)
        except Exception as exc:  # pragma: no cover - network/remote failures
            raise HTTPException(status_code=400, detail=f"Failed to capture screenshot: {exc}") from exc
        finally:
            await context.close()
            await browser.close()
    encoded = base64.b64encode(screenshot_bytes).decode("ascii")
    return ScreenshotTestResponse(image_data_url=f"data:image/png;base64,{encoded}")
