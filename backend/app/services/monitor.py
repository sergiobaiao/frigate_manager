from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from playwright.async_api import async_playwright
from sqlmodel import select

from ..config import ConfigManager
from ..database import get_session
from ..models import FailureEvent, Host
from ..services.logs import (
    estimate_failure_start,
    parse_log_entries,
    persist_log_entries,
    save_log_file,
)
from ..services.notifications import send_media, send_message
from ..utils.paths import LOG_DIR, SCREENSHOT_DIR
from ..utils.timezone import now_tz

logger = logging.getLogger(__name__)


async def _fetch_page_screenshot(page, output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(output_path), full_page=True)
    return str(output_path)


async def _detect_failed_cameras(page) -> Dict[str, List[str]]:
    await page.wait_for_timeout(2000)
    failed = await page.evaluate(
        """
        () => {
            const failureText = "No frames have been received, check error logs";
            const elements = Array.from(
                document.querySelectorAll('*')
            ).filter(el => el.textContent && el.textContent.includes(failureText));
            return elements.map(el => {
                const card = el.closest('[data-camera], .camera-card, article, section, div');
                let identifier = 'unknown';
                if (card) {
                    if (card.dataset && card.dataset.camera) {
                        identifier = card.dataset.camera;
                    } else if (card.id) {
                        identifier = card.id;
                    } else {
                        const heading = card.querySelector('h1, h2, h3, h4, h5, h6, .title');
                        if (heading && heading.textContent) {
                            identifier = heading.textContent.trim();
                        }
                    }
                }
                return identifier;
            });
        }
        """
    )
    return {"camera_ids": failed, "count": len(failed)}


async def check_host(host: Host, config_manager: ConfigManager) -> Optional[FailureEvent]:
    config = config_manager.get()
    timestamp = now_tz(config_manager.timezone)
    hostname = host.name
    first_screenshot: Optional[str] = None
    second_screenshot: Optional[str] = None
    failure_event: Optional[FailureEvent] = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(host.base_url, wait_until="networkidle", timeout=60000)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to load Frigate host %s: %s", host.base_url, exc)
            await browser.close()
            return None
        detection = await _detect_failed_cameras(page)
        if detection["count"] <= 1:
            await browser.close()
            return None
        first_path = SCREENSHOT_DIR / f"{hostname}-{timestamp.strftime('%Y%m%dT%H%M%S')}-initial.png"
        first_screenshot = await _fetch_page_screenshot(page, first_path)
        await browser.close()

    await asyncio.sleep(config.retry_delay_minutes * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(host.base_url, wait_until="networkidle", timeout=60000)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to load Frigate host on retry %s: %s", host.base_url, exc)
            await browser.close()
            return None
        second_detection = await _detect_failed_cameras(page)
        retry_timestamp = now_tz(config_manager.timezone)
        second_path = SCREENSHOT_DIR / f"{hostname}-{retry_timestamp.strftime('%Y%m%dT%H%M%S')}-retry.png"
        second_screenshot = await _fetch_page_screenshot(page, second_path)
        await browser.close()

    if second_detection["count"] <= 1:
        return None

    camera_ids = [str(identifier) for identifier in second_detection["camera_ids"]]

    services = ["go2rtc", "nginx", "frigate"]
    log_files: List[str] = []
    parsed_entries: Dict[str, List[dict]] = {}
    async with httpx.AsyncClient(timeout=60) as client:
        for service in services:
            url = f"{host.base_url}/api/logs/{service}"
            try:
                response = await client.get(url)
                response.raise_for_status()
                content = response.text
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to fetch log %s from %s: %s", service, host.base_url, exc)
                content = ""
            path = save_log_file(hostname, service, content, LOG_DIR)
            log_files.append(str(path))
            entries = parse_log_entries(content)
            parsed_entries[service] = entries
            with get_session() as session:
                persist_log_entries(session, host.id, service, entries)

    failure_start = None
    for service in services:
        estimate = estimate_failure_start(parsed_entries[service], config_manager.timezone)
        if estimate and (failure_start is None or estimate < failure_start):
            failure_start = estimate

    normalized_failure_start = None
    if failure_start:
        localized = (
            failure_start.astimezone(config_manager.timezone)
            if failure_start.tzinfo
            else failure_start.replace(tzinfo=config_manager.timezone)
        )
        normalized_failure_start = localized.replace(tzinfo=None)

    failure_event = FailureEvent(
        host_id=host.id,
        failure_count=second_detection["count"],
        camera_ids=camera_ids,
        failure_start=normalized_failure_start,
        first_screenshot_path=first_screenshot,
        second_screenshot_path=second_screenshot,
        log_files=log_files,
        created_at=datetime.utcnow(),
    )

    with get_session() as session:
        session.add(failure_event)
        session.commit()
        session.refresh(failure_event)

    message_lines = [
        f"<b>Frigate Manager Alert</b>",
        f"Host: <code>{hostname}</code>",
        f"Affected cameras: {second_detection['count']}",
        f"Identifiers: {', '.join(camera_ids)}",
    ]
    if normalized_failure_start:
        message_lines.append(
            f"Estimated start: {normalized_failure_start.strftime('%Y-%m-%d %H:%M:%S')} GMT-3"
        )
    if config.mention_name:
        message_lines.append(config.mention_name)
    if config.mention_user_ids:
        ids = [uid.strip() for uid in config.mention_user_ids.split(",") if uid.strip()]
        mentions = " ".join(f"<a href=\"tg://user?id={uid}\">.</a>" for uid in ids)
        message_lines.append(mentions)

    try:
        await send_message(config, "\n".join(message_lines))
    except Exception as exc:  # pragma: no cover - network
        logger.exception("Failed to send Telegram message: %s", exc)

    if first_screenshot and second_screenshot:
        try:
            await send_media(
                config,
                [first_screenshot, second_screenshot],
                media_type="photo",
            )
        except Exception as exc:  # pragma: no cover - network
            logger.exception("Failed to send Telegram screenshots: %s", exc)

    try:
        await send_media(config, log_files, media_type="document")
    except Exception as exc:  # pragma: no cover - network
        logger.exception("Failed to send Telegram logs: %s", exc)

    return failure_event


async def run_monitoring(config_manager: ConfigManager) -> None:
    with get_session() as session:
        hosts = session.exec(select(Host).where(Host.enabled == True)).all()  # noqa: E712
    tasks = [check_host(host, config_manager) for host in hosts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):  # pragma: no cover - logging
            logger.exception("Monitoring task raised an exception", exc_info=result)
