"""Каталог цветов плёнки и однотонные JPEG-референсы в static/img/wrap_solids/ (для API)."""

from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import WrapColorCatalog

_APP_DIR = Path(__file__).resolve().parent.parent
_WRAP_SOLIDS_REL = "img/wrap_solids"
_WRAP_SOLIDS_DIR = _APP_DIR / "static" / _WRAP_SOLIDS_REL
_SOLID_SIZE = 512


def normalize_hex(raw: str) -> str:
    s = (raw or "").strip().upper()
    if not s:
        raise ValueError("empty hex")
    if not s.startswith("#"):
        s = "#" + s
    if not re.fullmatch(r"^#[0-9A-F]{6}$", s):
        raise ValueError(f"invalid hex: {raw!r}")
    return s


def solid_filename_for_hex(hex_norm: str) -> str:
    hx = normalize_hex(hex_norm).lstrip("#").lower()
    return f"wrap_{hx}.jpg"


def solid_rel_path(hex_norm: str) -> str:
    return f"{_WRAP_SOLIDS_REL}/{solid_filename_for_hex(hex_norm)}"


def solid_filesystem_path(hex_norm: str) -> Path:
    return _WRAP_SOLIDS_DIR / solid_filename_for_hex(hex_norm)


def public_url_for_hex(hex_norm: str) -> str:
    rel = solid_rel_path(hex_norm).replace("\\", "/").lstrip("/")
    return f"/static/{rel}"


def _write_solid_jpeg(path: Path, rgb: tuple[int, int, int]) -> None:
    r, g, b = rgb
    # OpenCV: BGR; imwrite() на Windows падает на путях с кириллицей — пишем через imencode.
    img = np.zeros((_SOLID_SIZE, _SOLID_SIZE, 3), dtype=np.uint8)
    img[:, :] = (b, g, r)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(
        ".jpg",
        img,
        [int(cv2.IMWRITE_JPEG_QUALITY), 92],
    )
    if not ok:
        raise OSError(f"failed to encode wrap color reference: {path}")
    path.write_bytes(encoded.tobytes())


def ensure_solid_png(hex_norm: str) -> Path:
    """Создаёт однотонный JPEG-референс, если файла ещё нет (имя функции сохранено для совместимости)."""
    hx = normalize_hex(hex_norm)
    r = int(hx[1:3], 16)
    g = int(hx[3:5], 16)
    b = int(hx[5:7], 16)
    dest = solid_filesystem_path(hx)
    if dest.is_file() and dest.stat().st_size > 200:
        return dest
    # Старые PNG из ранней версии — пересоздаём в JPEG
    legacy_png = dest.with_suffix(".png")
    if legacy_png.is_file():
        try:
            legacy_png.unlink()
        except OSError:
            pass
    _write_solid_jpeg(dest, (r, g, b))
    return dest


def list_active_wrap_colors(session: Session) -> list[WrapColorCatalog]:
    return list(
        session.scalars(
            select(WrapColorCatalog)
            .where(WrapColorCatalog.is_active.is_(True))
            .order_by(WrapColorCatalog.sort_order, WrapColorCatalog.id)
        )
    )


def get_active_by_id(session: Session, catalog_id: int) -> WrapColorCatalog | None:
    row = session.get(WrapColorCatalog, catalog_id)
    if row is None or not row.is_active:
        return None
    return row
