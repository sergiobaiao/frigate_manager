from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional, TypedDict

import httpx
from playwright.async_api import async_playwright
from sqlmodel import select

from ..config import ConfigManager
from ..database import get_session
from ..models import FailureEvent, Host, HostCheck
from ..services.logs import (
    estimate_failure_start,
    parse_log_entries,
    persist_log_entries,
    save_log_file,
)
from ..services.notifications import send_media, send_message
from ..utils.paths import LOG_DIR, SCREENSHOT_DIR, TRACE_DIR
from ..utils.timezone import now_tz

logger = logging.getLogger(__name__)


class HostCheckResult(TypedDict):
    status: Literal["success", "failure", "error"]
    summary: str
    failure_event: Optional[FailureEvent]


async def _fetch_page_screenshot(page, output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(output_path), full_page=True)
    return str(output_path)


async def _start_tracing(context, recorder: Optional["HostCheckRecorder"], label: str) -> bool:
    try:
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
    except Exception as exc:  # pragma: no cover - optional feature
        logger.warning("Unable to start Playwright tracing (%s): %s", label, exc)
        if recorder:
            recorder.log(f"Unable to start Playwright tracing ({label}): {exc}")
        return False
    if recorder:
        recorder.log(f"Playwright tracing enabled for {label} run")
    return True


async def _stop_tracing(
    context,
    output_path: Path,
    recorder: Optional["HostCheckRecorder"],
    label: str,
) -> Optional[str]:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await context.tracing.stop(path=str(output_path))
    except Exception as exc:  # pragma: no cover - optional feature
        logger.warning("Unable to persist Playwright trace (%s): %s", label, exc)
        if recorder:
            recorder.log(f"Failed to save Playwright trace ({label}): {exc}")
        return None
    saved_path = str(output_path)
    if recorder:
        recorder.log(f"Saved Playwright trace for {label} run to {saved_path}")
    return saved_path


async def _detect_failed_cameras(page) -> List[str]:
    await page.wait_for_selector("body", timeout=30000)
    label_selectors = [
        '[data-testid="camera-title"]',
        '.camera-title',
        '.title',
        '.camera-header',
        '[data-camera-name]',
        '[data-testid="camera-name"]',
        'header h1',
        'header h2',
        'h1',
        'h2',
        'h3',
        'h4',
        'h5',
        'h6',
        'figcaption',
    ]
    failure_texts = [
        "no frames have been received",
        "no frames received",
        "camera offline",
        "camera is offline",
        "unable to load camera",
        "disconnected",
        "lost connection",
    ]
    failure_states = ["error", "offline", "failed"]

    async def _scan_once() -> List[str]:
        failed = await page.evaluate(
            """
            (failureTexts, failureStates, labelSelectors) => {
                const normalizedTexts = failureTexts.map((text) => text.toLowerCase());
                const normalizedStates = failureStates.map((state) => state.toLowerCase());
                const identifiers = [];
                const seen = new Set();

                const matches = [];

                const isFailureText = (content) => {
                    if (!content) {
                        return false;
                    }
                    const lower = content.toLowerCase();
                    return normalizedTexts.some((snippet) => lower.includes(snippet));
                };

                const registerMatch = (element) => {
                    if (!matches.includes(element)) {
                        matches.push(element);
                    }
                };

                const collectMatches = (root) => {
                    if (!root) {
                        return;
                    }
                    const walker = document.createTreeWalker(
                        root,
                        NodeFilter.SHOW_ELEMENT,
                        null,
                        false,
                    );
                    let current = walker.currentNode;
                    while (current) {
                        const el = current;
                        if (isFailureText(el.innerText) || isFailureText(el.textContent)) {
                            registerMatch(el);
                        } else {
                            const ariaLabel = el.getAttribute ? el.getAttribute('aria-label') : null;
                            if (isFailureText(ariaLabel)) {
                                registerMatch(el);
                            }
                        }

                        if (el.getAttribute) {
                            const dataState = el.getAttribute('data-state');
                            if (
                                dataState &&
                                normalizedStates.includes(dataState.toLowerCase())
                            ) {
                                registerMatch(el);
                            }
                        }

                        if (el.classList) {
                            for (const cls of el.classList) {
                                if (normalizedStates.includes(cls.toLowerCase())) {
                                    registerMatch(el);
                                    break;
                                }
                            }
                        }

                        if (el.shadowRoot) {
                            collectMatches(el.shadowRoot);
                        }

                        if (el.tagName === 'IFRAME' && el.contentDocument) {
                            collectMatches(el.contentDocument);
                        }

                        current = walker.nextNode();
                    }
                };

                collectMatches(document);

                const findCandidateContainer = (start) => {
                    let node = start;
                    while (node) {
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            const element = node;
                            const matchesSelector =
                                '[data-camera], [data-camera-id], article, section, figure, div, frigate-card, frigate-card-camera, frigate-card-camera-live, frigate-card-camera-state';
                            if (element.matches(matchesSelector)) {
                                return element;
                            }
                        }

                        if (node.parentElement) {
                            node = node.parentElement;
                            continue;
                        }
                        if (node.assignedSlot) {
                            node = node.assignedSlot;
                            continue;
                        }
                        const root = node.getRootNode ? node.getRootNode() : null;
                        if (root && root.host) {
                            node = root.host;
                            continue;
                        }
                        break;
                    }
                    return null;
                };

                matches.forEach((el, index) => {
                    const card = findCandidateContainer(el);
                    let identifier = '';
                    if (card) {
                        const datasetCamera = card.dataset ? card.dataset.camera : null;
                        const datasetCameraId = card.dataset ? card.dataset.cameraId : null;
                        if (datasetCamera) {
                            identifier = datasetCamera.trim();
                        }
                        if (!identifier && datasetCameraId) {
                            identifier = datasetCameraId.trim();
                        }
                        const directDataCamera = card.getAttribute('data-camera');
                        if (!identifier && directDataCamera) {
                            identifier = directDataCamera.trim();
                        }
                        const directDataCameraId = card.getAttribute('data-camera-id');
                        if (!identifier && directDataCameraId) {
                            identifier = directDataCameraId.trim();
                        }
                        if (!identifier && card.id) {
                            identifier = card.id.trim();
                        }
                        const ariaLabel = card.getAttribute('aria-label');
                        if (!identifier && ariaLabel) {
                            identifier = ariaLabel.trim();
                        }
                        if (!identifier) {
                            for (const selector of labelSelectors) {
                                const label = card.querySelector(selector);
                                if (
                                    label &&
                                    label.textContent &&
                                    label.textContent.trim()
                                ) {
                                    identifier = label.textContent.trim();
                                    break;
                                }
                            }
                        }
                    }
                    if (!identifier) {
                        identifier = `camera-${index + 1}`;
                    }
                    if (!seen.has(identifier)) {
                        seen.add(identifier);
                        identifiers.push(identifier);
                    }
                });

                return identifiers;
            }
            """,
            failure_texts,
            failure_states,
            label_selectors,
        )
        return [str(identifier) for identifier in failed]

    attempts = 10
    delay_ms = 1000
    last_result: List[str] = []
    for attempt in range(attempts):
        current = await _scan_once()
        if current:
            return current
        last_result = current
        await page.wait_for_timeout(delay_ms)
    return last_result


def create_host_check(host_id: int, trigger: str, config_manager: ConfigManager) -> HostCheck:
    now = datetime.utcnow()
    initial_message = "Manual check requested" if trigger == "manual" else "Scheduled check queued"
    check = HostCheck(
        host_id=host_id,
        trigger=trigger,
        status="pending",
        log=[
            {
                "timestamp": now_tz(config_manager.timezone).isoformat(),
                "message": initial_message,
            }
        ],
        created_at=now,
        updated_at=now,
    )
    with get_session() as session:
        session.add(check)
        session.commit()
        session.refresh(check)
        return check


def _update_check_record(
    check_id: int,
    timezone,
    *,
    status: Optional[str] = None,
    summary: Optional[str] = None,
    message: Optional[str] = None,
    mark_started: bool = False,
    finished: bool = False,
    failure_event_id: Optional[int] = None,
) -> Optional[HostCheck]:
    with get_session() as session:
        check = session.get(HostCheck, check_id)
        if not check:
            return None
        log_entries = list(check.log or [])
        if message:
            log_entries.append({"timestamp": now_tz(timezone).isoformat(), "message": message})
            check.log = log_entries
        if status:
            check.status = status
        if summary is not None:
            check.summary = summary
        if mark_started and check.started_at is None:
            check.started_at = datetime.utcnow()
        if finished:
            check.finished_at = datetime.utcnow()
        if failure_event_id is not None:
            check.failure_event_id = failure_event_id
        check.updated_at = datetime.utcnow()
        session.add(check)
        session.commit()
        session.refresh(check)
        return check


class HostCheckRecorder:
    def __init__(self, check_id: int, config_manager: ConfigManager) -> None:
        self.check_id = check_id
        self.timezone = config_manager.timezone

    def start(self, host_name: str) -> None:
        _update_check_record(
            self.check_id,
            self.timezone,
            status="running",
            message=f"Starting check for {host_name}",
            mark_started=True,
        )

    def log(self, message: str) -> None:
        _update_check_record(self.check_id, self.timezone, message=message)

    def complete(
        self,
        status: str,
        summary: str,
        *,
        failure_event_id: Optional[int] = None,
    ) -> None:
        _update_check_record(
            self.check_id,
            self.timezone,
            status=status,
            summary=summary,
            finished=True,
            failure_event_id=failure_event_id,
        )

    def skip(self, summary: str) -> None:
        _update_check_record(
            self.check_id,
            self.timezone,
            status="skipped",
            summary=summary,
            finished=True,
        )


async def run_host_check(check_id: int, config_manager: ConfigManager) -> None:
    recorder = HostCheckRecorder(check_id, config_manager)
    with get_session() as session:
        check = session.get(HostCheck, check_id)
        if not check:
            return
        host = session.get(Host, check.host_id)
    if not host:
        recorder.log("Host was removed before the check could run.")
        recorder.complete("error", "Host not found")
        return
    if check.trigger == "scheduled" and not host.enabled:
        recorder.log("Host disabled; skipping scheduled check.")
        recorder.skip("Host disabled")
        return

    recorder.start(host.name)
    try:
        result = await check_host(host, config_manager, recorder=recorder)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Monitoring task raised an exception for host %s", host.name, exc_info=exc)
        recorder.log(f"Unexpected error: {exc}")
        recorder.complete("error", "Unexpected error during check")
        return

    summary = result["summary"]
    recorder.log(summary)
    if result["status"] == "failure":
        failure_event = result["failure_event"]
        failure_id = failure_event.id if failure_event else None
        recorder.complete("failure", summary, failure_event_id=failure_id)
    elif result["status"] == "success":
        recorder.complete("success", summary)
    else:
        recorder.complete("error", summary)


def queue_host_check(host_id: int, config_manager: ConfigManager, trigger: str = "manual") -> HostCheck:
    check = create_host_check(host_id, trigger, config_manager)
    asyncio.create_task(
        run_host_check(check.id, config_manager),
        name=f"host-check-{host_id}-{trigger}",
    )
    return check


async def check_host(
    host: Host,
    config_manager: ConfigManager,
    *,
    recorder: Optional[HostCheckRecorder] = None,
) -> HostCheckResult:
    config = config_manager.get()
    timezone = config_manager.timezone
    timestamp = now_tz(timezone)
    hostname = host.name
    first_screenshot: Optional[str] = None
    second_screenshot: Optional[str] = None
    trace_files: List[str] = []
    debug_mode = getattr(config, "debug_mode", False)
    if recorder and debug_mode:
        recorder.log("Debug mode enabled: additional Playwright traces will be captured")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        console_messages: List[str] = []
        initial_trace_started = False

        if recorder:
            def _capture_console(message) -> None:
                entry = f"[{message.type}] {message.text}"
                console_messages.append(entry)
                if len(console_messages) > 25:
                    del console_messages[0]

            page.on("console", _capture_console)
        if debug_mode:
            initial_trace_started = await _start_tracing(context, recorder, "initial")
        if recorder:
            recorder.log("Loading Frigate dashboard")
        try:
            await page.goto(host.base_url, wait_until="networkidle", timeout=60000)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to load Frigate host %s: %s", host.base_url, exc)
            if recorder:
                recorder.log(f"Failed to load dashboard: {exc}")
            if debug_mode and initial_trace_started:
                trace_path = TRACE_DIR / f"{hostname}-{timestamp.strftime('%Y%m%dT%H%M%S')}-initial-trace.zip"
                if saved := await _stop_tracing(context, trace_path, recorder, "initial"):
                    trace_files.append(saved)
            await context.close()
            await browser.close()
            return {
                "status": "error",
                "summary": "Unable to load Frigate dashboard",
                "failure_event": None,
            }
        initial_failed = await _detect_failed_cameras(page)
        if recorder:
            recorder.log(
                f"Initial scan detected {len(initial_failed)} failing cameras via dashboard inspection"
            )
        if not initial_failed:
            if debug_mode and initial_trace_started:
                trace_path = TRACE_DIR / f"{hostname}-{timestamp.strftime('%Y%m%dT%H%M%S')}-initial-trace.zip"
                if saved := await _stop_tracing(context, trace_path, recorder, "initial"):
                    trace_files.append(saved)
            await context.close()
            await browser.close()
            return {
                "status": "success",
                "summary": "No failing cameras detected",
                "failure_event": None,
            }
        first_path = SCREENSHOT_DIR / f"{hostname}-{timestamp.strftime('%Y%m%dT%H%M%S')}-initial.png"
        first_screenshot = await _fetch_page_screenshot(page, first_path)
        if recorder:
            recorder.log(f"Captured initial screenshot at {first_screenshot}")
            preview = "; ".join(console_messages[-5:])[:500]
            recorder.log(
                f"Recent browser console output: {preview}"
                if preview
                else "No browser console output captured"
            )
        if debug_mode and initial_trace_started:
            trace_path = TRACE_DIR / f"{hostname}-{timestamp.strftime('%Y%m%dT%H%M%S')}-initial-trace.zip"
            if saved := await _stop_tracing(context, trace_path, recorder, "initial"):
                trace_files.append(saved)
        await context.close()
        await browser.close()

    if recorder:
        recorder.log(f"Waiting {config.retry_delay_minutes} minutes before retry")
    await asyncio.sleep(config.retry_delay_minutes * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        retry_console_messages: List[str] = []
        retry_trace_started = False

        if recorder:
            def _capture_retry_console(message) -> None:
                entry = f"[{message.type}] {message.text}"
                retry_console_messages.append(entry)
                if len(retry_console_messages) > 25:
                    del retry_console_messages[0]

            page.on("console", _capture_retry_console)
        if debug_mode:
            retry_trace_started = await _start_tracing(context, recorder, "retry")
        if recorder:
            recorder.log("Retrying Frigate dashboard after delay")
        try:
            await page.goto(host.base_url, wait_until="networkidle", timeout=60000)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to load Frigate host on retry %s: %s", host.base_url, exc)
            if recorder:
                recorder.log(f"Retry failed to load dashboard: {exc}")
            if debug_mode and retry_trace_started:
                retry_trace_path = TRACE_DIR / f"{hostname}-{now_tz(timezone).strftime('%Y%m%dT%H%M%S')}-retry-trace.zip"
                if saved := await _stop_tracing(context, retry_trace_path, recorder, "retry"):
                    trace_files.append(saved)
            await context.close()
            await browser.close()
            return {
                "status": "error",
                "summary": "Retry failed to load dashboard",
                "failure_event": None,
            }
        retry_failed_ids = sorted(await _detect_failed_cameras(page))
        if recorder:
            recorder.log(
                f"Retry detected {len(retry_failed_ids)} failing cameras via dashboard inspection"
            )
        retry_timestamp = now_tz(timezone)
        second_path = SCREENSHOT_DIR / f"{hostname}-{retry_timestamp.strftime('%Y%m%dT%H%M%S')}-retry.png"
        second_screenshot = await _fetch_page_screenshot(page, second_path)
        if recorder:
            recorder.log(f"Captured retry screenshot at {second_screenshot}")
            retry_preview = "; ".join(retry_console_messages[-5:])[:500]
            recorder.log(
                f"Recent browser console output on retry: {retry_preview}"
                if retry_preview
                else "No browser console output captured on retry"
            )
        if debug_mode and retry_trace_started:
            retry_trace_path = TRACE_DIR / f"{hostname}-{retry_timestamp.strftime('%Y%m%dT%H%M%S')}-retry-trace.zip"
            if saved := await _stop_tracing(context, retry_trace_path, recorder, "retry"):
                trace_files.append(saved)
        await context.close()
        await browser.close()

    if not retry_failed_ids:
        return {
            "status": "success",
            "summary": "Issue cleared before retry completed",
            "failure_event": None,
        }

    camera_ids = retry_failed_ids
    if recorder:
        recorder.log(
            "Failure persists for %s cameras: %s"
            % (len(camera_ids), ", ".join(camera_ids))
        )

    services = ["go2rtc", "nginx", "frigate"]
    log_files: List[str] = []
    parsed_entries: Dict[str, List[dict]] = {}
    async with httpx.AsyncClient(timeout=60) as client:
        for service in services:
            url = f"{host.base_url}/api/logs/{service}"
            if recorder:
                recorder.log(f"Fetching {service} logs")
            try:
                response = await client.get(url)
                response.raise_for_status()
                content = response.text
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to fetch log %s from %s: %s", service, host.base_url, exc)
                if recorder:
                    recorder.log(f"Failed to fetch {service} logs: {exc}")
                content = ""
            path = save_log_file(hostname, service, content, LOG_DIR)
            log_files.append(str(path))
            entries = parse_log_entries(content)
            parsed_entries[service] = entries
            with get_session() as session:
                persist_log_entries(session, host.id, service, entries)
            if recorder:
                recorder.log(
                    f"Saved {service} logs to {path}" if content else f"No {service} log content retrieved"
                )

    if trace_files:
        log_files.extend(trace_files)

    failure_start = None
    for service in services:
        estimate = estimate_failure_start(parsed_entries.get(service, []), timezone)
        if estimate and (failure_start is None or estimate < failure_start):
            failure_start = estimate

    normalized_failure_start = None
    if failure_start:
        localized = (
            failure_start.astimezone(timezone)
            if failure_start.tzinfo
            else failure_start.replace(tzinfo=timezone)
        )
        normalized_failure_start = localized.replace(tzinfo=None)

    failure_event = FailureEvent(
        host_id=host.id,
        failure_count=len(camera_ids),
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

    summary = f"Detected {len(camera_ids)} failing cameras"
    if recorder:
        recorder.log("Failure recorded and notifications scheduled")

    message_lines = [
        f"<b>Frigate Manager Alert</b>",
        f"Host: <code>{hostname}</code>",
        f"Affected cameras: {len(camera_ids)}",
        f"Identifiers: {', '.join(camera_ids)}",
    ]
    if normalized_failure_start:
        message_lines.append(
            f"Estimated start: {normalized_failure_start.strftime('%Y-%m-%d %H:%M:%S')} GMT-3"
        )
    config = config_manager.get()
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
        if recorder:
            recorder.log(f"Telegram message failed: {exc}")

    if first_screenshot and second_screenshot:
        try:
            await send_media(
                config,
                [first_screenshot, second_screenshot],
                media_type="photo",
            )
        except Exception as exc:  # pragma: no cover - network
            logger.exception("Failed to send Telegram screenshots: %s", exc)
            if recorder:
                recorder.log(f"Screenshot upload failed: {exc}")

    try:
        await send_media(config, log_files, media_type="document")
    except Exception as exc:  # pragma: no cover - network
        logger.exception("Failed to send Telegram logs: %s", exc)
        if recorder:
            recorder.log(f"Log upload failed: {exc}")

    return {
        "status": "failure",
        "summary": summary,
        "failure_event": failure_event,
    }


async def run_monitoring(config_manager: ConfigManager) -> None:
    with get_session() as session:
        hosts = session.exec(select(Host).where(Host.enabled == True)).all()  # noqa: E712
    tasks: List[asyncio.Task[None]] = []
    for host in hosts:
        check = create_host_check(host.id, "scheduled", config_manager)
        tasks.append(asyncio.create_task(run_host_check(check.id, config_manager)))
    if not tasks:
        return
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):  # pragma: no cover - logging
            logger.exception("Monitoring task raised an exception", exc_info=result)
