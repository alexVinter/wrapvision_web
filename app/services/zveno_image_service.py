from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable

import httpx

logger = logging.getLogger(__name__)

_ZVENO_MAX_ATTEMPTS = max(1, int(os.getenv("ZVENO_MAX_ATTEMPTS", "3")))
_ZVENO_RETRY_DELAY_SEC = float(os.getenv("ZVENO_RETRY_DELAY_SEC", "0.75"))


class ZvenoImageServiceError(RuntimeError):
    """Ошибка при обращении к Zveno image API."""


class ZvenoImageService:
    """Сервис генерации изображения через Zveno OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = (api_key or os.getenv("ZVENO_API_KEY", "")).strip()
        self._base_url = (
            base_url or os.getenv("ZVENO_BASE_URL", "https://api.zveno.ai/v1")
        ).strip()
        self._model = (
            model or os.getenv("ZVENO_MODEL", "google/gemini-3.1-flash-image-preview")
        ).strip()

        if not self._api_key:
            raise ZvenoImageServiceError("ZVENO_API_KEY is not configured")
        if not self._base_url:
            raise ZvenoImageServiceError("ZVENO_BASE_URL is not configured")
        if not self._model:
            raise ZvenoImageServiceError("ZVENO_MODEL is not configured")

    def generate_image_bytes(
        self,
        *,
        ordered_image_paths: Iterable[Path],
        final_prompt: str,
    ) -> bytes:
        content: list[dict[str, object]] = [{"type": "text", "text": final_prompt}]
        for path in ordered_image_paths:
            raw = Path(path).read_bytes()
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _to_data_url(path=Path(path), raw=raw)},
                }
            )

        payload: dict[str, Any] = {
            "model": self._model,
            "modalities": ["image", "text"],
            "messages": [{"role": "user", "content": content}],
        }
        # Если шлюз отвечает 400 Unknown field — установите ZVENO_DISABLE_TOOL_CHOICE=1
        if os.getenv("ZVENO_DISABLE_TOOL_CHOICE", "").strip().lower() not in (
            "1",
            "true",
            "yes",
        ):
            payload["tool_choice"] = "none"

        url = f"{self._base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}"}

        last_preview = ""
        try:
            with httpx.Client(timeout=90) as client:
                for attempt in range(1, _ZVENO_MAX_ATTEMPTS + 1):
                    try:
                        response = client.post(url, json=payload, headers=headers)
                        response.raise_for_status()
                        data = response.json()
                    except httpx.HTTPStatusError as exc:
                        body = exc.response.text.strip()
                        details = body[:600] if body else str(exc)
                        raise ZvenoImageServiceError(
                            f"Zveno request failed with status {exc.response.status_code}: {details}"
                        ) from exc

                    image_bytes = _extract_image_bytes(data)
                    if image_bytes:
                        return image_bytes

                    last_preview = _response_preview(data)
                    if attempt < _ZVENO_MAX_ATTEMPTS and _zveno_response_retryable(data):
                        logger.warning(
                            "Zveno: нет изображения в ответе (попытка %s/%s), повтор: %s",
                            attempt,
                            _ZVENO_MAX_ATTEMPTS,
                            last_preview[:280],
                        )
                        time.sleep(_ZVENO_RETRY_DELAY_SEC * attempt)
                        continue
                    break
        except ZvenoImageServiceError:
            raise
        except Exception as exc:  # pragma: no cover
            raise ZvenoImageServiceError(f"Zveno request failed: {exc}") from exc

        raise ZvenoImageServiceError(
            f"Zveno response does not contain image data. Response preview: {last_preview}"
        )


def _zveno_response_retryable(data: object) -> bool:
    """Пустой контент или finish_reason=error часто временные (особенно MALFORMED_FUNCTION_CALL)."""
    if not isinstance(data, dict):
        return True
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) == 0:
        return True
    ch0 = choices[0]
    if not isinstance(ch0, dict):
        return True
    finish = str(ch0.get("finish_reason") or "").lower()
    if finish in ("error", "length"):
        return True
    native = str(ch0.get("native_finish_reason") or "")
    if native == "MALFORMED_FUNCTION_CALL":
        return True
    message = ch0.get("message")
    if isinstance(message, dict):
        msg_content = message.get("content")
        if isinstance(msg_content, list) and len(msg_content) == 0:
            return True
    return False


def _to_data_url(path: Path, raw: bytes) -> str:
    mime = _guess_mime_type(path)
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extract_image_bytes(data: object) -> bytes | None:
    if not isinstance(data, dict):
        return None

    maybe_direct = _extract_from_data_array(data.get("data"))
    if maybe_direct:
        return maybe_direct

    choices = data.get("choices")
    if not isinstance(choices, list):
        return None

    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        maybe_image = _extract_from_message(message)
        if maybe_image:
            return maybe_image
    return None


def _extract_from_message(message: dict[str, object]) -> bytes | None:
    maybe_image = _extract_from_images_array(message.get("images"))
    if maybe_image:
        return maybe_image

    content = message.get("content")
    maybe_image = _extract_from_content(content)
    if maybe_image:
        return maybe_image

    return _extract_from_urlish_text(_stringify_jsonish(message))


def _extract_from_content(content: object) -> bytes | None:
    if isinstance(content, str):
        parsed = _decode_base64_maybe(content)
        if parsed:
            return parsed
        return _extract_from_urlish_text(content)

    if not isinstance(content, list):
        return None

    for part in content:
        if not isinstance(part, dict):
            continue
        image_b64 = part.get("image_base64") or part.get("b64_json")
        if isinstance(image_b64, str):
            parsed = _decode_base64_maybe(image_b64)
            if parsed:
                return parsed

        # Some providers wrap output image as {"type":"output_image","image_url":"..."}.
        image_url_raw = part.get("image_url")
        if isinstance(image_url_raw, str):
            parsed = _extract_from_urlish_text(image_url_raw)
            if parsed:
                return parsed

        image_url = image_url_raw
        if isinstance(image_url, dict):
            url = image_url.get("url")
            if isinstance(url, str):
                parsed = _decode_data_url(url)
                if parsed:
                    return parsed
                parsed = _download_image_url(url)
                if parsed:
                    return parsed

        text_val = part.get("text")
        if isinstance(text_val, str):
            parsed = _extract_from_urlish_text(text_val)
            if parsed:
                return parsed

    return None


def _extract_from_images_array(images: object) -> bytes | None:
    if not isinstance(images, list):
        return None

    for item in images:
        if not isinstance(item, dict):
            continue
        b64 = item.get("b64_json") or item.get("image_base64")
        if isinstance(b64, str):
            parsed = _decode_base64_maybe(b64)
            if parsed:
                return parsed
        url = item.get("url") or item.get("image_url")
        if isinstance(url, str):
            parsed = _extract_from_urlish_text(url)
            if parsed:
                return parsed
    return None


def _extract_from_data_array(data_arr: object) -> bytes | None:
    if not isinstance(data_arr, list):
        return None
    for item in data_arr:
        if isinstance(item, dict):
            b64 = item.get("b64_json") or item.get("image_base64")
            if isinstance(b64, str):
                parsed = _decode_base64_maybe(b64)
                if parsed:
                    return parsed
            url = item.get("url")
            if isinstance(url, str):
                parsed = _extract_from_urlish_text(url)
                if parsed:
                    return parsed
    return None


def _extract_from_urlish_text(text: str) -> bytes | None:
    data_bytes = _decode_data_url(text.strip())
    if data_bytes:
        return data_bytes

    urls = re.findall(r"https?://[^\s)>\"]+", text)
    for url in urls:
        parsed = _download_image_url(url)
        if parsed:
            return parsed
    return None


def _decode_data_url(value: str) -> bytes | None:
    if not value.startswith("data:"):
        return None
    _, _, payload = value.partition(",")
    if not payload:
        return None
    return _decode_base64_maybe(payload)


def _decode_base64_maybe(value: str) -> bytes | None:
    clean = value.strip()
    if not clean:
        return None
    try:
        return base64.b64decode(clean, validate=True)
    except Exception:
        return None


def _download_image_url(url: str) -> bytes | None:
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            ctype = response.headers.get("content-type", "").lower()
            if ctype.startswith("image/") and response.content:
                return response.content
    except Exception:
        return None
    return None


def _stringify_jsonish(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=True)
    except Exception:
        return str(value)


def _response_preview(data: object) -> str:
    try:
        return json.dumps(data, ensure_ascii=True)[:800]
    except Exception:
        return str(data)[:800]


def _guess_mime_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    return "application/octet-stream"
