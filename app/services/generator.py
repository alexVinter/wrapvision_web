"""
Модуль запуска генерации изображения.

Модуль получает подготовленный список изображений и итоговый prompt,
передает данные во внешний сервис генерации и возвращает путь к результату.
При недоступности внешнего сервиса используется резервное изображение.
"""

import uuid
from dataclasses import dataclass
import logging
from pathlib import Path

from app.services.zveno_image_service import ZvenoImageService, ZvenoImageServiceError

_APP_DIR = Path(__file__).resolve().parent.parent
DEMO_RESULT_PATH = _APP_DIR / "static" / "img" / "demo_result.jpg"
_UPLOADS_DIR = _APP_DIR.parent / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)

RESULT_IMAGE_URL = "/static/img/demo_result.jpg"


def is_demo_fallback_result(image_url_or_path: str | None) -> bool:
    """Истина, если в БД сохранён путь к демо-заглушке (fallback при ошибке API)."""
    u = (image_url_or_path or "").strip().split("?", 1)[0]
    return u == RESULT_IMAGE_URL or u.endswith("/demo_result.jpg")


def is_upload_api_generation_result(image_url_or_path: str | None) -> bool:
    """Истина для успешного ответа Zveno: файл в uploads с префиксом generated_."""
    u = (image_url_or_path or "").strip().split("?", 1)[0]
    return bool(u.startswith("/uploads/generated_"))


@dataclass(frozen=True)
class GenerationInput:
    """Вход для генерации: фиксированный порядок картинок + собранный промпт.

    Порядок путей и текст промпта собираются в prompt_builder из флагов wrap_needed / wheels_needed;
    согласованность с файлами проверяется там и в POST /generate до вызова generate_result.
    """

    ordered_image_paths: tuple[Path, ...]
    wheels_enabled: bool
    final_prompt: str


class DemoResultMissingError(FileNotFoundError):
    """Нет app/static/img/demo_result.jpg — покажите пользователю понятное сообщение."""


def generate_result(data: GenerationInput) -> Path:
    """
    Мок: не вызывает внешний API.

    Входные данные для внешнего сервиса: data.ordered_image_paths, data.final_prompt.
    """
    _ = data.wheels_enabled
    try:
        service = ZvenoImageService()
        image_bytes = service.generate_image_bytes(
            ordered_image_paths=data.ordered_image_paths,
            final_prompt=data.final_prompt,
        )
        generated = _UPLOADS_DIR / f"generated_{uuid.uuid4().hex[:12]}.png"
        generated.write_bytes(image_bytes)
        return generated
    except ZvenoImageServiceError as exc:
        logger.warning(
            "Генерация через Zveno не удалась (показана демо-заглушка demo_result.jpg): %s",
            exc,
        )
        if not DEMO_RESULT_PATH.is_file():
            raise DemoResultMissingError(
                "Не найден файл демонстрационного результата "
                f"({DEMO_RESULT_PATH.name}). Положите изображение в app/static/img/."
            )
        return DEMO_RESULT_PATH


def result_path_to_url(path: Path) -> str:
    if path == DEMO_RESULT_PATH:
        return RESULT_IMAGE_URL
    if path.parent == _UPLOADS_DIR:
        return f"/uploads/{path.name}"
    return RESULT_IMAGE_URL
