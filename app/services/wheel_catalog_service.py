"""Каталог дисков: пути к файлам в static для промпта и превью."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import WheelCatalog

_APP_STATIC = Path(__file__).resolve().parent.parent / "static"


def list_wheels(session: Session) -> list[WheelCatalog]:
    return list(
        session.scalars(
            select(WheelCatalog).order_by(WheelCatalog.sort_order, WheelCatalog.id)
        )
    )


def filesystem_path(session: Session, catalog_id: int) -> Path | None:
    row = session.get(WheelCatalog, catalog_id)
    if row is None:
        return None
    rel = row.image_rel_path.replace("\\", "/").lstrip("/")
    p = _APP_STATIC / rel
    return p if p.is_file() else None


def public_url(row: WheelCatalog) -> str:
    rel = row.image_rel_path.replace("\\", "/").lstrip("/")
    return f"/static/{rel}"
