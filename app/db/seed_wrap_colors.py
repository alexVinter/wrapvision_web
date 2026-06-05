"""Сид каталога цветов плёнки (hex)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import WrapColorCatalog

_DEFAULT_COLORS: list[tuple[str, str, int]] = [
    ("Белый глянец", "#FFFFFF", 0),
    ("Чёрный глянец", "#0D0D0D", 1),
    ("Серый Nardo", "#6B6F72", 2),
    ("Красный", "#C41E3A", 3),
    ("Синий металлик", "#1E3A8A", 4),
    ("Зелёный British", "#004225", 5),
    ("Жёлтый", "#FFD700", 6),
    ("Оранжевый", "#FF6B00", 7),
    ("Фиолетовый", "#6B21A8", 8),
    ("Бордовый", "#722F37", 9),
    ("Бежевый", "#C4A77D", 10),
    ("Серебро", "#C0C0C0", 11),
]


def ensure_wrap_color_catalog(session: Session) -> None:
    n = session.scalar(select(func.count()).select_from(WrapColorCatalog)) or 0
    if n > 0:
        return
    for name, hx, order in _DEFAULT_COLORS:
        session.add(
            WrapColorCatalog(
                name=name,
                hex_code=hx,
                is_active=True,
                sort_order=order,
            )
        )
    session.commit()
