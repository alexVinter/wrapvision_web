"""
Удаление из таблицы projects «мусорных» записей (демо-заглушка, пустой результат, старые пути).

Запуск из корня проекта (где лежит папка app/):

  .venv\\Scripts\\python cleanup_demo_projects.py --dry-run
  .venv\\Scripts\\python cleanup_demo_projects.py --mode demo
  .venv\\Scripts\\python cleanup_demo_projects.py --mode non_api

Режимы:
  demo     — только явная демо-картинка (/static/img/demo_result.jpg) и пустой result_image_path.
  non_api  — всё, что НЕ успешный файл /uploads/generated_* (включая demo, NULL, произвольные пути).
"""

from __future__ import annotations

import argparse

from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import Project
from app.services.generator import (
    is_demo_fallback_result,
    is_upload_api_generation_result,
)


def _match_delete(path: str | None, mode: str) -> bool:
    if mode == "demo":
        if path is None or not str(path).strip():
            return True
        return is_demo_fallback_result(path)
    if mode == "non_api":
        return not is_upload_api_generation_result(path)
    raise ValueError(f"unknown mode {mode!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Удалить проекты с демо/не-API результатом.")
    parser.add_argument(
        "--mode",
        choices=("demo", "non_api"),
        default="demo",
        help="demo — только заглушка и пустой путь; non_api — всё кроме /uploads/generated_*",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать id и путь, без удаления",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        rows = session.execute(select(Project.id, Project.result_image_path)).all()
        to_delete = [
            int(rid)
            for rid, path in rows
            if _match_delete(path, args.mode)
        ]

    print(f"mode={args.mode} matched projects: {len(to_delete)}")
    if not to_delete:
        return

    preview = to_delete[:40]
    print("ids (first 40):", preview)
    if len(to_delete) > 40:
        print(f"... and {len(to_delete) - 40} more")

    if args.dry_run:
        print("dry-run: no rows deleted")
        return

    with SessionLocal() as session:
        session.execute(delete(Project).where(Project.id.in_(to_delete)))
        session.commit()
    print("deleted.")


if __name__ == "__main__":
    main()
