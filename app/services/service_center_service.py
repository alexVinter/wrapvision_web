"""
Каталог автомастерских по городу.

Seed: реальные партнёры, координаты подобраны по адресу (однократный geocoding, Photon).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import ServiceCenter


def normalize_city(value: str) -> str:
    return " ".join(value.strip().split())


# Ключ каталога: (name, city). Записи вне этого набора удаляются при ensure_demo_centers.
_SERVICE_CENTER_SEED: list[dict[str, Any]] = [
    # Москва (координаты по адресу, Photon komoot.io)
    {
        "name": "ОКЛЕЙКИН.РУ",
        "city": "Москва",
        "address": "г. Москва, ул. Ташкентская, д. 28, стр. 1",
        "phone": "+7 (495) 003-07-03",
        "website": "https://www.okleikin.ru/",
        "latitude": 55.6991107,
        "longitude": 37.806062,
        "is_active": True,
        "description": None,
    },
    {
        "name": "OKLEYKA.PRO",
        "city": "Москва",
        "address": "г. Москва, ул. Автозаводская, 23к7",
        "phone": "+7 (495) 868-27-72",
        "website": "https://okleyka.pro/",
        "latitude": 55.7073446,
        "longitude": 37.6577684,
        "is_active": True,
        "description": None,
    },
    {
        "name": "BY-TUNING",
        "city": "Москва",
        "address": "г. Москва, 8-й проезд Марьиной Рощи, 30с1",
        "phone": "+7 (495) 789-02-50",
        "website": "https://by-tuning.ru/",
        "latitude": 55.8011045,
        "longitude": 37.6048488,
        "is_active": True,
        "description": None,
    },
    # Санкт-Петербург
    {
        "name": "Performance Detailing",
        "city": "Санкт-Петербург",
        "address": "Санкт-Петербург, Приморский проспект, 72",
        "phone": "+7 (921) 906-09-07",
        "website": "https://performance-spb.ru/",
        "latitude": 59.9807209,
        "longitude": 30.2104069,
        "is_active": True,
        "description": None,
    },
    {
        "name": "ОКЛЕЙКА",
        "city": "Санкт-Петербург",
        "address": "Санкт-Петербург, ул. Уральская, 13Ж",
        "phone": "+7 (981) 950-95-52",
        "website": "https://okley-spb.ru/",
        "latitude": 59.9535938,
        "longitude": 30.2619224,
        "is_active": True,
        "description": None,
    },
    {
        "name": "Skolof",
        "city": "Санкт-Петербург",
        "address": "Санкт-Петербург, ул. Салова, 57к1",
        "phone": "+7 (812) 425-68-04",
        "website": "https://skolof.net/",
        "latitude": 59.8856448,
        "longitude": 30.3750974,
        "is_active": True,
        "description": None,
    },
    # Красноярск
    {
        "name": "Tarbey",
        "city": "Красноярск",
        "address": "г. Красноярск, проспект Металлургов, 2М",
        "phone": "+7 (904) 897-02-45",
        "website": "https://tarbey.ru/",
        "latitude": 56.0611367,
        "longitude": 92.9686998,
        "is_active": True,
        "description": None,
    },
    {
        "name": "Project Wrap Detailing",
        "city": "Красноярск",
        "address": "Красноярск, ул. Маерчака, 51/2",
        "phone": "+7 (906) 910-33-97",
        "website": "https://projectwrap.ru/",
        "latitude": 56.0291662,
        "longitude": 92.827344,
        "is_active": True,
        "description": None,
    },
    # Казань
    {
        "name": "VinylKZN",
        "city": "Казань",
        "address": "Казань, ул. Мусина, 29, ГСК «Мотор», бокс 1101",
        "phone": "+7 (843) 245-26-46",
        "website": "https://vinylkzn.ru/",
        "latitude": 55.8256779,
        "longitude": 49.1200115,
        "is_active": True,
        "description": None,
    },
    {
        "name": "Urban Detailing",
        "city": "Казань",
        "address": "Казань, ул. Островского, 98",
        "phone": "+7 (843) 211-91-14",
        "website": "https://urban-detailing.ru/",
        "latitude": 55.7792566,
        "longitude": 49.1322242,
        "is_active": True,
        "description": None,
    },
    {
        "name": "Vinyl Style Казань",
        "city": "Казань",
        "address": "Казань, ул. Гаврилова, 10А",
        "phone": "+7 (843) 253-73-03",
        "website": "https://vinylkazan.ru/",
        "latitude": 55.8297409,
        "longitude": 49.160053,
        "is_active": True,
        "description": None,
    },
    # Новосибирск
    {
        "name": "Vinyl Style",
        "city": "Новосибирск",
        "address": "Новосибирск, ул. Богдана Хмельницкого, 5/1",
        "phone": "+7 (383) 291-12-46",
        "website": "https://vinylstyle.ru/",
        "latitude": 55.0670936,
        "longitude": 82.9354077,
        "is_active": True,
        "description": None,
    },
    {
        "name": "Craft Siberian Workshop",
        "city": "Новосибирск",
        "address": "Новосибирск, ул. Салтыкова-Щедрина, 128",
        "phone": "+7 (960) 783-83-85",
        "website": "https://craftsw.com/",
        "latitude": 55.0405847,
        "longitude": 82.8985289,
        "is_active": True,
        "description": None,
    },
    {
        "name": "ТонировкаПрофи",
        "city": "Новосибирск",
        "address": "г. Новосибирск, ул. Кропоткина, 92/3",
        "phone": "+7 (383) 210-69-06",
        "website": "https://54tonirovka.ru/",
        "latitude": 55.0533233,
        "longitude": 82.908926,
        "is_active": True,
        "description": None,
    },
]

_SEED_KEYS: set[tuple[str, str]] = {(r["name"], r["city"]) for r in _SERVICE_CENTER_SEED}


def fetch_centers_by_city(session: Session, city: str) -> list[ServiceCenter]:
    """Активные мастерские города (без учёта регистра)."""
    needle = normalize_city(city).casefold()
    if not needle:
        return []
    stmt: Select[tuple[ServiceCenter]] = select(ServiceCenter).order_by(ServiceCenter.name)
    rows = list(session.scalars(stmt).all())
    return [
        sc
        for sc in rows
        if normalize_city(sc.city or "").casefold() == needle
        and sc.is_active
    ]


def ensure_demo_centers(session: Session) -> None:
    """Синхронизирует каталог: удаляет записи вне seed, upsert по (name, city)."""
    for sc in list(session.scalars(select(ServiceCenter)).all()):
        if (sc.name, sc.city) not in _SEED_KEYS:
            session.delete(sc)
    session.flush()

    for row in _SERVICE_CENTER_SEED:
        stmt = select(ServiceCenter).where(
            ServiceCenter.name == row["name"],
            ServiceCenter.city == row["city"],
        )
        existing = session.scalar(stmt)
        if existing is None:
            session.add(
                ServiceCenter(
                    name=row["name"],
                    city=row["city"],
                    address=row.get("address"),
                    phone=row.get("phone"),
                    website=row.get("website"),
                    description=row.get("description"),
                    latitude=row.get("latitude"),
                    longitude=row.get("longitude"),
                    is_active=bool(row.get("is_active", True)),
                )
            )
        else:
            existing.address = row.get("address")
            existing.phone = row.get("phone")
            existing.website = row.get("website")
            existing.description = row.get("description")
            existing.latitude = row.get("latitude")
            existing.longitude = row.get("longitude")
            existing.is_active = bool(row.get("is_active", True))
    session.commit()
