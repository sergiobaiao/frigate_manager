from __future__ import annotations

import asyncio
import io
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict

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


_OCR_BACKEND_LOCK = threading.Lock()
_OCR_BACKEND: Optional[str] = None
_OCR_BACKEND_ERROR: Optional[str] = None
_PYTESSERACT: Any = None
_EASYOCR: Any = None
_EASYOCR_READER: Any = None


def _ensure_ocr_backend() -> Optional[str]:
    global _OCR_BACKEND, _OCR_BACKEND_ERROR, _PYTESSERACT, _EASYOCR, _EASYOCR_READER

    if _OCR_BACKEND is not None or _OCR_BACKEND_ERROR is not None:
        return _OCR_BACKEND

    with _OCR_BACKEND_LOCK:
        if _OCR_BACKEND is not None or _OCR_BACKEND_ERROR is not None:
            return _OCR_BACKEND

        backend_errors: List[str] = []

        try:  # pragma: no cover - exercised in integration tests
            import pytesseract  # type: ignore

            pytesseract.get_tesseract_version()
            _PYTESSERACT = pytesseract
            _OCR_BACKEND = "pytesseract"
            logger.debug("Using pytesseract for camera failure OCR checks")
            return _OCR_BACKEND
        except Exception as exc:  # pragma: no cover - optional dependency
            backend_errors.append(f"pytesseract: {exc}")
            logger.info(
                "pytesseract OCR backend unavailable for camera checks: %s",
                exc,
            )

        try:  # pragma: no cover - optional dependency
            import easyocr  # type: ignore

            _EASYOCR = easyocr
            _EASYOCR_READER = easyocr.Reader(["en"], gpu=False)
            _OCR_BACKEND = "easyocr"
            logger.info("Falling back to easyocr for camera failure OCR checks")
            return _OCR_BACKEND
        except Exception as exc:  # pragma: no cover - optional dependency
            backend_errors.append(f"easyocr: {exc}")
            logger.error(
                "Camera failure detection OCR backends unavailable: %s",
                "; ".join(backend_errors),
            )
            _OCR_BACKEND_ERROR = "; ".join(backend_errors)
            return None


def _read_text_from_image(image_bytes: bytes, backend: str) -> str:
    try:
        from PIL import Image, ImageFilter, ImageOps  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.error("Pillow is required for OCR image handling: %s", exc)
        return ""

    if backend == "pytesseract" and _PYTESSERACT is not None:
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                grayscale = image.convert("L")
                enhanced = ImageOps.autocontrast(grayscale)
                enhanced = ImageOps.equalize(enhanced)
                enhanced = enhanced.filter(ImageFilter.SHARPEN)
                text = _PYTESSERACT.image_to_string(enhanced)
                return " ".join(text.split())
        except Exception as exc:  # pragma: no cover - runtime protection
            logger.debug("OCR extraction failed (pytesseract): %s", exc)
        return ""

    if backend == "easyocr" and _EASYOCR_READER is not None:
        try:
            import numpy as np  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.error("NumPy is required for easyocr image handling: %s", exc)
            return ""

        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                normalized = ImageOps.autocontrast(image.convert("RGB"))
                array = np.array(normalized)
        except Exception as exc:  # pragma: no cover - runtime protection
            logger.debug("Unable to prepare image for easyocr: %s", exc)
            return ""

        try:
            results = _EASYOCR_READER.readtext(array, detail=0)
        except Exception as exc:  # pragma: no cover - runtime protection
            logger.debug("easyocr extraction failed: %s", exc)
            return ""

        combined = " ".join(str(item) for item in results)
        return " ".join(combined.split())

    return ""


async def _capture_container_image(page, container_id: str) -> Optional[bytes]:
    selector = f'[data-fm-detector-id="{container_id}"]'
    handle = await page.query_selector(selector)
    if not handle:
        return None

    try:
        await handle.scroll_into_view_if_needed()
        return await handle.screenshot(type="png")
    except Exception as exc:  # pragma: no cover - runtime protection
        logger.debug("Unable to capture screenshot for analysis (%s): %s", selector, exc)
        return None


def _detect_placeholder_frame(image_bytes: bytes) -> Optional[bool]:
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.debug("Pillow is required for placeholder detection: %s", exc)
        return None

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            grayscale = image.convert("L")
            histogram = grayscale.histogram()
    except Exception as exc:  # pragma: no cover - runtime protection
        logger.debug("Unable to analyze image for placeholder detection: %s", exc)
        return None

    total = sum(histogram)
    if total <= 0:
        return None

    dark_count = sum(histogram[:32])
    bright_count = sum(histogram[200:])
    mean_intensity = sum(index * count for index, count in enumerate(histogram)) / total

    dark_ratio = dark_count / total
    bright_ratio = bright_count / total

    if dark_ratio >= 0.9 and bright_ratio <= 0.05 and mean_intensity <= 40:
        return True
    return False


async def _extract_text_via_ocr(page, container_id: str, backend: str) -> str:
    image_bytes = await _capture_container_image(page, container_id)
    if not image_bytes:
        return ""
    return await asyncio.to_thread(_read_text_from_image, image_bytes, backend)


def _contains_failure_text(text: str, failure_texts: List[str]) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(snippet in lower for snippet in failure_texts)


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
    container_selectors = [
        '[data-testid="camera-card"]',
        '[data-testid="camera-tile"]',
        '[data-testid="camera"]',
        '[data-camera]',
        '[data-camera-id]',
        '[data-camera-name]',
        '[data-testid="frigate-card-camera"]',
        'frigate-card',
        'frigate-card-camera',
        'frigate-card-camera-live',
        'frigate-card-camera-state',
        'frigate-card-live',
        'frigate-card-viewer',
        '.camera-card',
        '.camera-tile',
        '.camera',
        'article',
        'section',
        'figure',
    ]
    failure_texts = [
        "no frames have been received",
        "no frames received",
        "check error logs",
        "error logs",
        "camera offline",
        "camera is offline",
        "unable to load camera",
        "disconnected",
        "lost connection",
        "no signal",
    ]
    failure_image_hints = [
        "no-frame",
        "no_frame",
        "no-frames",
        "offline",
        "camera-offline",
        "camera_offline",
        "error",
    ]
    failure_states = ["error", "offline", "failed"]

    async def _scan_once() -> List[Dict[str, Any]]:
        result = await page.evaluate(
            """
            (args) => {
                const {
                    failureTexts,
                    failureStates,
                    failureImageHints,
                    labelSelectors,
                    containerSelectors,
                } = args;
                const normalizedTexts = failureTexts.map((text) => text.toLowerCase());
                const normalizedStates = failureStates.map((state) => state.toLowerCase());
                const normalizedImageHints = failureImageHints.map((hint) => hint.toLowerCase());

                const pushUnique = (array, value) => {
                    if (value === null || value === undefined) {
                        return;
                    }
                    if (typeof value === 'string') {
                        const trimmed = value.trim();
                        if (!trimmed) {
                            return;
                        }
                        if (!array.includes(trimmed)) {
                            array.push(trimmed);
                        }
                        return;
                    }
                    if (!array.includes(value)) {
                        array.push(value);
                    }
                };

                let idCounter = 0;
                const ensureElementId = (element) => {
                    if (!element || element.nodeType !== Node.ELEMENT_NODE) {
                        return null;
                    }
                    if (!element.dataset.fmDetectorId) {
                        idCounter += 1;
                        const identifier = `fm-detector-${idCounter}`;
                        element.dataset.fmDetectorId = identifier;
                        element.setAttribute('data-fm-detector-id', identifier);
                    }
                    return element.dataset.fmDetectorId;
                };

                const isFailureText = (content) => {
                    if (!content) {
                        return false;
                    }
                    const lower = String(content).toLowerCase();
                    return normalizedTexts.some((snippet) => lower.includes(snippet));
                };

                const ariaLabelFromIds = (element, attribute) => {
                    if (!element || !element.getAttribute) {
                        return null;
                    }
                    const idList = element.getAttribute(attribute);
                    if (!idList) {
                        return null;
                    }
                    const ids = idList.split(/\s+/).filter(Boolean);
                    const ownerDocument = element.ownerDocument || document;
                    for (const id of ids) {
                        if (!ownerDocument) {
                            continue;
                        }
                        const ref = ownerDocument.getElementById(id);
                        if (ref && ref.textContent) {
                            const text = ref.textContent.trim();
                            if (text) {
                                return text;
                            }
                        }
                    }
                    return null;
                };

                const collectSourceHint = (element) => {
                    if (!element) {
                        return null;
                    }
                    const sources = [];
                    if (element.currentSrc) {
                        sources.push(element.currentSrc);
                    }
                    if (element.src) {
                        sources.push(element.src);
                    }
                    if (element.srcset) {
                        sources.push(element.srcset);
                    }
                    const combined = sources.join(' ').toLowerCase();
                    if (!combined) {
                        return null;
                    }
                    for (const hint of normalizedImageHints) {
                        if (combined.includes(hint)) {
                            return hint;
                        }
                    }
                    return null;
                };

                const isVisibleElement = (element) => {
                    if (!element || typeof element !== 'object') {
                        return false;
                    }
                    try {
                        if (element.classList && element.classList.contains('invisible')) {
                            return false;
                        }
                        const style = window.getComputedStyle(element);
                        if (style) {
                            const visibility = style.getPropertyValue('visibility');
                            const display = style.getPropertyValue('display');
                            const opacity = parseFloat(style.getPropertyValue('opacity') || '1');
                            if (visibility === 'hidden' || display === 'none' || opacity <= 0.05) {
                                return false;
                            }
                        }
                        if (element.getBoundingClientRect) {
                            const rect = element.getBoundingClientRect();
                            if (!rect || rect.width <= 1 || rect.height <= 1) {
                                return false;
                            }
                        }
                    } catch (error) {
                        return true;
                    }
                    return true;
                };

                const hasFailureBackground = (element) => {
                    if (!element || element.nodeType !== Node.ELEMENT_NODE) {
                        return null;
                    }
                    try {
                        const style = window.getComputedStyle(element);
                        if (!style) {
                            return null;
                        }
                        const backgroundImage = style.getPropertyValue('background-image');
                        if (!backgroundImage) {
                            return null;
                        }
                        const lower = backgroundImage.toLowerCase();
                        for (const hint of normalizedImageHints) {
                            if (lower.includes(hint)) {
                                return hint;
                            }
                        }
                    } catch (error) {
                        return null;
                    }
                    return null;
                };

                const deepVisit = (root, callback) => {
                    if (!root) {
                        return;
                    }
                    const stack = [root];
                    const visited = new Set();
                    while (stack.length > 0) {
                        const node = stack.pop();
                        if (!node || visited.has(node)) {
                            continue;
                        }
                        visited.add(node);

                        if (node.nodeType === Node.ELEMENT_NODE) {
                            callback(node);

                            if (node.shadowRoot) {
                                stack.push(node.shadowRoot);
                            }

                            if (node.tagName === 'SLOT') {
                                const assigned = node.assignedNodes
                                    ? node.assignedNodes({ flatten: true })
                                    : [];
                                for (let i = assigned.length - 1; i >= 0; i -= 1) {
                                    stack.push(assigned[i]);
                                }
                            }
                        }

                        if (node.childNodes) {
                            for (let i = node.childNodes.length - 1; i >= 0; i -= 1) {
                                stack.push(node.childNodes[i]);
                            }
                        }
                    }
                };

                const allElements = [];
                deepVisit(document, (element) => {
                    allElements.push(element);
                });

                const labelMap = new Map();
                const potentialContainers = new Set();

                const findCandidateContainer = (start) => {
                    let node = start;
                    while (node) {
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            const element = node;
                            if (
                                containerSelectors.some((selector) => {
                                    try {
                                        return element.matches(selector);
                                    } catch (error) {
                                        return false;
                                    }
                                })
                            ) {
                                return element;
                            }
                        }
                        if (node.parentElement) {
                            node = node.parentElement;
                        } else if (node.assignedSlot) {
                            node = node.assignedSlot;
                        } else {
                            const root = node.getRootNode ? node.getRootNode() : null;
                            if (root && root.host) {
                                node = root.host;
                            } else {
                                break;
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

                allElements.forEach((element) => {
                    for (const selector of labelSelectors) {
                        try {
                            if (!element.matches(selector)) {
                                continue;
                            }
                        } catch (error) {
                            continue;
                        }
                        const container = findCandidateContainer(element);
                        if (!container) {
                            continue;
                        }
                        potentialContainers.add(container);
                        const textContent = element.textContent ? element.textContent.trim() : '';
                        if (textContent) {
                            const existing = labelMap.get(container) || [];
                            if (!existing.includes(textContent)) {
                                existing.push(textContent);
                                labelMap.set(container, existing);
                            }
                        }
                        break;
                    }
                });

                allElements.forEach((element) => {
                    for (const selector of containerSelectors) {
                        try {
                            if (element.matches(selector)) {
                                potentialContainers.add(element);
                                break;
                            }
                        } catch (error) {
                            continue;
                        }
                    }
                });

                const containers = Array.from(potentialContainers).filter(
                    (el) => el && el.nodeType === Node.ELEMENT_NODE,
                );
                const limitedContainers = containers.slice(0, 50);
                const results = [];

                const inspectElement = (root, info) => {
                    if (!root) {
                        return;
                    }
                    const stack = [root];
                    const inspected = new Set();
                    while (stack.length > 0) {
                        const node = stack.pop();
                        if (!node || inspected.has(node)) {
                            continue;
                        }
                        inspected.add(node);

                        if (node.nodeType !== Node.ELEMENT_NODE) {
                            if (node.childNodes) {
                                for (let i = node.childNodes.length - 1; i >= 0; i -= 1) {
                                    stack.push(node.childNodes[i]);
                                }
                            }
                            continue;
                        }

                        const element = node;

                        if (!info.hasVisualContent) {
                            const tagName = element.tagName || '';
                            if (['IMG', 'CANVAS', 'VIDEO', 'PICTURE', 'SVG'].includes(tagName)) {
                                if (isVisibleElement(element)) {
                                    info.hasVisualContent = true;
                                } else {
                                    pushUnique(info.hiddenVisuals, tagName.toLowerCase());
                                }
                            }
                        }

                        const backgroundHint = hasFailureBackground(element);
                        if (backgroundHint) {
                            info.hasVisualContent = true;
                            pushUnique(info.imageHints, `background:${backgroundHint}`);
                        }

                        const sourceHint = collectSourceHint(element);
                        if (sourceHint) {
                            info.hasVisualContent = true;
                            pushUnique(info.imageHints, `source:${sourceHint}`);
                        }

                        const textContent = element.innerText || element.textContent;
                        if (isFailureText(textContent)) {
                            pushUnique(info.textMatches, String(textContent).trim().slice(0, 160));
                        } else if (element.getAttribute) {
                            const ariaLabel = element.getAttribute('aria-label');
                            if (isFailureText(ariaLabel)) {
                                pushUnique(info.textMatches, ariaLabel.trim().slice(0, 160));
                            } else if (ariaLabel && ariaLabel.toLowerCase().includes('loading')) {
                                pushUnique(info.stateMatches, `aria:${ariaLabel.trim().slice(0, 80)}`);
                            }
                            const ariaDescription = element.getAttribute('aria-description');
                            if (isFailureText(ariaDescription)) {
                                pushUnique(info.textMatches, ariaDescription.trim().slice(0, 160));
                            } else if (ariaDescription && ariaDescription.toLowerCase().includes('loading')) {
                                pushUnique(info.stateMatches, `aria:${ariaDescription.trim().slice(0, 80)}`);
                            }
                            const labelledBy = ariaLabelFromIds(element, 'aria-labelledby');
                            if (isFailureText(labelledBy)) {
                                pushUnique(info.textMatches, labelledBy.slice(0, 160));
                            } else if (labelledBy && labelledBy.toLowerCase().includes('loading')) {
                                pushUnique(info.stateMatches, `aria:${labelledBy.slice(0, 80)}`);
                            }
                            const describedBy = ariaLabelFromIds(element, 'aria-describedby');
                            if (isFailureText(describedBy)) {
                                pushUnique(info.textMatches, describedBy.slice(0, 160));
                            } else if (describedBy && describedBy.toLowerCase().includes('loading')) {
                                pushUnique(info.stateMatches, `aria:${describedBy.slice(0, 80)}`);
                            }
                            const titleAttr = element.getAttribute('title');
                            if (isFailureText(titleAttr)) {
                                pushUnique(info.textMatches, titleAttr.trim().slice(0, 160));
                            }
                            const altAttr = element.getAttribute('alt');
                            if (isFailureText(altAttr)) {
                                pushUnique(info.textMatches, altAttr.trim().slice(0, 160));
                            }

                            const dataState = element.getAttribute('data-state');
                            if (dataState && normalizedStates.includes(dataState.toLowerCase())) {
                                pushUnique(info.stateMatches, `data-state:${dataState}`);
                            }
                            const dataStatus = element.getAttribute('data-status');
                            if (dataStatus && normalizedStates.includes(dataStatus.toLowerCase())) {
                                pushUnique(info.stateMatches, `data-status:${dataStatus}`);
                            }
                        }

                        if (element.dataset) {
                            const datasetState = element.dataset.state;
                            if (datasetState && normalizedStates.includes(String(datasetState).toLowerCase())) {
                                pushUnique(info.stateMatches, `dataset.state:${datasetState}`);
                            }
                            const datasetStatus = element.dataset.status;
                            if (datasetStatus && normalizedStates.includes(String(datasetStatus).toLowerCase())) {
                                pushUnique(info.stateMatches, `dataset.status:${datasetStatus}`);
                            }
                        }

                        if (element.classList) {
                            element.classList.forEach((cls) => {
                                if (normalizedStates.includes(cls.toLowerCase())) {
                                    pushUnique(info.stateMatches, `class:${cls}`);
                                }
                                if (cls.toLowerCase().includes('spin')) {
                                    pushUnique(info.stateMatches, `spinner:${cls}`);
                                }
                            });
                        }

                        if (element.shadowRoot) {
                            stack.push(element.shadowRoot);
                        }

                        if (element.tagName === 'IFRAME' && element.contentDocument) {
                            stack.push(element.contentDocument);
                        }

                        if (element.tagName === 'SLOT') {
                            const assigned = element.assignedNodes
                                ? element.assignedNodes({ flatten: true })
                                : [];
                            for (let i = assigned.length - 1; i >= 0; i -= 1) {
                                stack.push(assigned[i]);
                            }
                        }

                        if (element.childNodes) {
                            for (let i = element.childNodes.length - 1; i >= 0; i -= 1) {
                                stack.push(element.childNodes[i]);
                            }
                        }
                    }
                };

                limitedContainers.forEach((container, index) => {
                    const containerId = ensureElementId(container);
                    if (!containerId) {
                        return;
                    }

                    const labelTexts = [];
                    const mapped = labelMap.get(container) || [];
                    mapped.forEach((text) => pushUnique(labelTexts, text));
                    labelSelectors.forEach((selector) => {
                        try {
                            container.querySelectorAll(selector).forEach((label) => {
                                if (label && label.textContent) {
                                    pushUnique(labelTexts, label.textContent.trim());
                                }
                            });
                        } catch (error) {
                            // Ignore invalid selectors
                        }
                    });

                    let identifier = '';
                    if (container.dataset) {
                        if (container.dataset.camera) {
                            identifier = container.dataset.camera.trim();
                        } else if (container.dataset.cameraId) {
                            identifier = container.dataset.cameraId.trim();
                        } else if (container.dataset.cameraName) {
                            identifier = container.dataset.cameraName.trim();
                        }
                    }
                    if (!identifier && container.getAttribute) {
                        const directCamera = container.getAttribute('data-camera');
                        const directCameraId = container.getAttribute('data-camera-id');
                        if (directCamera) {
                            identifier = directCamera.trim();
                        } else if (directCameraId) {
                            identifier = directCameraId.trim();
                        }
                    }
                    if (!identifier && container.id) {
                        identifier = container.id.trim();
                    }
                    if (!identifier && container.getAttribute) {
                        const ariaLabel = container.getAttribute('aria-label');
                        if (ariaLabel) {
                            identifier = ariaLabel.trim();
                        }
                    }
                    if (!identifier && labelTexts.length > 0) {
                        identifier = labelTexts[0];
                    }
                    if (!identifier) {
                        identifier = `camera-${index + 1}`;
                    }

                    const info = {
                        containerId,
                        identifier,
                        labelTexts,
                        textMatches: [],
                        stateMatches: [],
                        imageHints: [],
                        hasVisualContent: false,
                        hiddenVisuals: [],
                    };

                    inspectElement(container, info);

                    if (!info.hasVisualContent) {
                        const backgroundHint = hasFailureBackground(container);
                        if (backgroundHint) {
                            info.hasVisualContent = true;
                            pushUnique(info.imageHints, `background:${backgroundHint}`);
                        }
                    }

                    results.push(info);
                });

                return results;
            }
            """,
            {
                "failureTexts": failure_texts,
                "failureStates": failure_states,
                "failureImageHints": failure_image_hints,
                "labelSelectors": label_selectors,
                "containerSelectors": container_selectors,
            },
        )
        if not isinstance(result, list):
            return []
        return result

    attempts = 10
    delay_ms = 1000
    last_result: List[str] = []
    hidden_visual_counts: Dict[str, int] = {}
    hidden_visual_threshold = 6
    placeholder_counts: Dict[str, int] = {}
    placeholder_start_attempt = 4
    placeholder_threshold = 3
    for attempt in range(attempts):
        scan_results = await _scan_once()
        seen_identifiers: set[str] = set()
        failures: List[str] = []
        ocr_candidates: List[Dict[str, Any]] = []

        for entry in scan_results:
            identifier = str(entry.get("identifier") or "").strip()
            if not identifier:
                continue

            text_matches = entry.get("textMatches") or []
            raw_state_matches = entry.get("stateMatches") or []
            spinner_matches = [
                state
                for state in raw_state_matches
                if "spinner" in state.lower() or "loading" in state.lower()
            ]
            state_matches = [
                state for state in raw_state_matches if state not in spinner_matches
            ]

            if text_matches or state_matches:
                if identifier not in seen_identifiers:
                    seen_identifiers.add(identifier)
                    failures.append(identifier)
                continue

            if entry.get("hasVisualContent"):
                hidden_visual_counts.pop(identifier, None)
            else:
                hidden_visuals = entry.get("hiddenVisuals") or []
                if (hidden_visuals or spinner_matches) and attempt >= 2:
                    count = hidden_visual_counts.get(identifier, 0) + 1
                    hidden_visual_counts[identifier] = count
                    if count >= hidden_visual_threshold and identifier not in seen_identifiers:
                        seen_identifiers.add(identifier)
                        failures.append(identifier)
                        logger.debug(
                            "Detected failed camera due to missing visual content (%s): hidden=%s states=%s",
                            identifier,
                            ",".join(str(item) for item in hidden_visuals[:5]) or "none",
                            ",".join(spinner_matches[:5]) or "none",
                        )
                        continue
                else:
                    hidden_visual_counts.pop(identifier, None)

            if entry.get("containerId"):
                ocr_candidates.append(entry)

        if ocr_candidates:
            backend = _ensure_ocr_backend()
            prioritized: List[Dict[str, Any]] = []
            prioritized.extend(
                [candidate for candidate in ocr_candidates if candidate.get("imageHints")]
            )
            prioritized.extend(
                [candidate for candidate in ocr_candidates if not candidate.get("imageHints")]
            )

            seen_containers: set[str] = set()
            for candidate in prioritized:
                container_id = candidate.get("containerId")
                if not container_id or container_id in seen_containers:
                    continue
                seen_containers.add(container_id)

                image_bytes = await _capture_container_image(page, container_id)
                if not image_bytes:
                    continue

                placeholder = _detect_placeholder_frame(image_bytes)
                identifier = str(candidate.get("identifier") or "").strip()
                if placeholder and identifier:
                    if attempt >= placeholder_start_attempt:
                        count = placeholder_counts.get(identifier, 0) + 1
                        placeholder_counts[identifier] = count
                        if count >= placeholder_threshold and identifier not in seen_identifiers:
                            seen_identifiers.add(identifier)
                            failures.append(identifier)
                            logger.debug(
                                "Detected failed camera via placeholder analysis (%s)",
                                identifier,
                            )
                            continue
                elif identifier and identifier in placeholder_counts:
                    placeholder_counts.pop(identifier, None)

                if not backend:
                    continue

                text = await asyncio.to_thread(_read_text_from_image, image_bytes, backend)
                if not text:
                    continue

                cleaned_text = text.replace("\n", " ").strip()

                if _contains_failure_text(cleaned_text, failure_texts):
                    identifier = str(candidate.get("identifier") or "").strip()
                    if identifier and identifier not in seen_identifiers:
                        seen_identifiers.add(identifier)
                        failures.append(identifier)
                        logger.debug(
                            "Detected failed camera via OCR (%s): %s",
                            identifier,
                            cleaned_text[:240],
                        )
                else:
                    identifier = str(candidate.get("identifier") or "").strip()
                    label_texts = candidate.get("labelTexts") or []
                    if identifier:
                        logger.debug(
                            "OCR text for %s did not match failure keywords: %s",
                            identifier,
                            cleaned_text[:240],
                        )
                    elif label_texts:
                        logger.debug(
                            "OCR text for camera labeled %s did not match failure keywords: %s",
                            ", ".join(str(label) for label in label_texts),
                            cleaned_text[:240],
                        )

            if not backend:
                logger.debug(
                    "Skipping OCR-based camera failure detection because no backend is available",
                )

        if failures:
            return failures

        last_result = failures
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
