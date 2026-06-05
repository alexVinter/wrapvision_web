"""Создание таблиц SQLite (MVP). Запуск: python -m app.db.init_db из корня проекта."""

from sqlalchemy import inspect, text

from app.db import models  # noqa: F401 — регистрация моделей в metadata
from app.db.database import Base, engine


def _migrate_sqlite_light() -> None:
    """
    create_all() не добавляет колонки в уже существующие таблицы.
    Добавляем недостающие поля для старых файлов wrapvision.db (MVP).
    """
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    with engine.begin() as conn:
        if insp.has_table("projects"):
            cols = {c["name"] for c in insp.get_columns("projects")}
            if "final_prompt" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN final_prompt TEXT"))
            if "city" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN city VARCHAR(128)"))
            if "user_id" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN user_id INTEGER"))
            if "result_image_path" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN result_image_path VARCHAR(512)"))
            if "car_upload_name" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN car_upload_name VARCHAR(512)"))
            if "wrap_upload_name" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN wrap_upload_name VARCHAR(512)"))
            if "wheel_upload_name" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN wheel_upload_name VARCHAR(512)"))
            if "wheels_enabled" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN wheels_enabled BOOLEAN"))
            if "wheel_source" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN wheel_source VARCHAR(16)"))
            if "wheel_catalog_id" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN wheel_catalog_id INTEGER"))
            if "wheel_reference_image_path" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE projects ADD COLUMN wheel_reference_image_path VARCHAR(512)"
                    )
                )
            if "wrap_film_source" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN wrap_film_source VARCHAR(24)"))
            if "wrap_color_catalog_id" not in cols:
                conn.execute(
                    text("ALTER TABLE projects ADD COLUMN wrap_color_catalog_id INTEGER")
                )

        if insp.has_table("service_centers"):
            cols_sc = {c["name"] for c in insp.get_columns("service_centers")}
            if "city" not in cols_sc:
                conn.execute(text("ALTER TABLE service_centers ADD COLUMN city VARCHAR(128)"))
            if "phone" not in cols_sc:
                conn.execute(text("ALTER TABLE service_centers ADD COLUMN phone VARCHAR(64)"))
            if "website" not in cols_sc:
                conn.execute(text("ALTER TABLE service_centers ADD COLUMN website VARCHAR(512)"))
            if "description" not in cols_sc:
                conn.execute(text("ALTER TABLE service_centers ADD COLUMN description TEXT"))
            if "latitude" not in cols_sc:
                conn.execute(text("ALTER TABLE service_centers ADD COLUMN latitude FLOAT"))
            if "longitude" not in cols_sc:
                conn.execute(text("ALTER TABLE service_centers ADD COLUMN longitude FLOAT"))
            if "is_active" not in cols_sc:
                conn.execute(
                    text(
                        "ALTER TABLE service_centers ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"
                    )
                )


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_light()


if __name__ == "__main__":
    init_db()
    print("Таблицы созданы:", ", ".join(Base.metadata.tables.keys()))
