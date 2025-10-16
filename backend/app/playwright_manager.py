from __future__ import annotations

import asyncio
from typing import Optional, Tuple

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


class PlaywrightManager:
    def __init__(self) -> None:
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> Browser:
        async with self._lock:
            if self._browser is None:
                playwright = await async_playwright().start()
                self._playwright = playwright
                self._browser = await playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                    ],
                )
        assert self._browser is not None
        return self._browser

    async def open_page(self) -> Tuple[BrowserContext, Page]:
        browser = await self._ensure_browser()
        context = await browser.new_context()
        page = await context.new_page()
        return context, page

    async def close(self) -> None:
        async with self._lock:
            if self._browser is not None:
                await self._browser.close()
                self._browser = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None


__all__ = ["PlaywrightManager"]
