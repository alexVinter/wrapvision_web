"""Каталог дисков по файлам в static/img/wheels/ и синхронизация с БД."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Project, WheelCatalog

_STATIC_IMG = Path(__file__).resolve().parent.parent / "static" / "img"
_WHEELS_DIR = _STATIC_IMG / "wheels"
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})


def _normalize_rel(rel: str) -> str:
    return rel.replace("\\", "/").lstrip("/")


def _rel_from_filename(name: str) -> str:
    return f"img/wheels/{name}"


def _title_for_filename(filename: str) -> str:
    stem = Path(filename).stem
    return ("Каталог · " + stem)[:128]


def ensure_wheel_catalog(session: Session) -> None:
    """Синхронизирует строки WheelCatalog с реальными файлами в static/img/wheels.

    Запросы генерации сохраняют wheel_catalog_id; для удалённых с файловой системы записей
    foreign key на проектах обнуляется, затем строка каталога удаляется.
    """
    _WHEELS_DIR.mkdir(parents=True, exist_ok=True)

    disk_files = [
        p
        for p in _WHEELS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
    ]
    disk_files.sort(key=lambda p: p.name.casefold())

    paths_ordered = [_rel_from_filename(p.name) for p in disk_files]
    paths_expected = set(paths_ordered)

    rows_all = list(session.scalars(select(WheelCatalog)))
    by_path = {_normalize_rel(r.image_rel_path): r for r in rows_all}

    orphan_paths = [
        path for path in by_path if path not in paths_expected
    ]
    if orphan_paths:
        orphan_ids = [by_path[path].id for path in orphan_paths]
        session.execute(
            update(Project)
            .where(Project.wheel_catalog_id.in_(orphan_ids))
            .values(wheel_catalog_id=None)
        )
        for oid in orphan_ids:
            row = session.get(WheelCatalog, oid)
            if row is not None:
                session.delete(row)
        session.flush()

        rows_all = list(session.scalars(select(WheelCatalog)))
        by_path = {_normalize_rel(r.image_rel_path): r for r in rows_all}

    for order, rel in enumerate(paths_ordered):
        title = _title_for_filename(rel.split("/")[-1])
        row = by_path.get(rel)
        if row is not None:
            row.sort_order = order
            if row.title != title:
                row.title = title
        else:
            session.add(
                WheelCatalog(title=title, image_rel_path=rel, sort_order=order)
            )

    session.commit()
