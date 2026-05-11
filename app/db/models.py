"""
Модели под новый сценарий генерации.

- generation_mode: standard | custom_idea
- idea_prompt: текст пользовательской идеи (режим custom_idea), не «старые пожелания»
- access_status: доступ к премиум-режиму custom_idea (locked / unlocked / …)
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class GenerationMode(str, enum.Enum):
    standard = "standard"
    custom_idea = "custom_idea"


class AccessStatus(str, enum.Enum):
    """Доступ к custom_idea. unlocked — после проверки кода / будущей оплаты."""

    locked = "locked"
    unlocked = "unlocked"
    allowed = "allowed"
    pending = "pending"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )

    projects: Mapped[list["Project"]] = relationship(back_populates="user")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )

    projects: Mapped[list[Project]] = relationship(back_populates="client")


class WheelCatalog(Base):
    """Справочник изображений дисков (файлы в static)."""

    __tablename__ = "wheel_catalog"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128))
    image_rel_path: Mapped[str] = mapped_column(String(512))
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")

    projects: Mapped[list["Project"]] = relationship(back_populates="wheel_catalog")


class ServiceCenter(Base):
    __tablename__ = "service_centers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )

    projects: Mapped[list[Project]] = relationship(back_populates="service_center")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    service_center_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_centers.id"), nullable=True, index=True
    )

    generation_mode: Mapped[str] = mapped_column(
        String(32),
        default=GenerationMode.standard.value,
        server_default=GenerationMode.standard.value,
    )
    idea_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    access_status: Mapped[str] = mapped_column(
        String(32),
        default=AccessStatus.locked.value,
        server_default=AccessStatus.locked.value,
    )

    result_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    car_upload_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    wrap_upload_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    wheel_upload_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    wheels_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    wheel_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    wheel_catalog_id: Mapped[int | None] = mapped_column(
        ForeignKey("wheel_catalog.id"), nullable=True, index=True
    )
    wheel_reference_image_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now()
    )

    client: Mapped[Client] = relationship(back_populates="projects")
    user: Mapped["User | None"] = relationship(back_populates="projects")
    service_center: Mapped[ServiceCenter | None] = relationship(
        back_populates="projects"
    )
    wheel_catalog: Mapped["WheelCatalog | None"] = relationship(
        back_populates="projects"
    )
