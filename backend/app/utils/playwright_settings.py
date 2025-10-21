"""Shared Playwright launch configuration for screenshot captures."""

from __future__ import annotations

# Chromium launch arguments validated against the production environment.
PLAYWRIGHT_LAUNCH_ARGS = [
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

# A consistent viewport keeps screenshots deterministic while still capturing the
# complete dashboard by combining it with ``full_page=True`` when saving.
PLAYWRIGHT_VIEWPORT = {"width": 1920, "height": 1080}

