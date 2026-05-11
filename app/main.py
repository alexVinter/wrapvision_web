import html
import os
import random
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

import jinja2
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.db.database import SESSION_SECRET_KEY, SessionLocal
from app.db.init_db import init_db
from app.db.models import AccessStatus, Client, GenerationMode, Project, User, WheelCatalog
from app.db.seed_wheels import ensure_wheel_catalog
from app.services.generator import (
    DemoResultMissingError,
    GenerationInput,
    RESULT_IMAGE_URL,
    generate_result,
    is_upload_api_generation_result,
    result_path_to_url,
)
from app.services.prompt_builder import (
    build_final_prompt,
    build_ordered_image_paths,
)
from app.services.auth_service import (
    create_user,
    get_or_create_client_for_user,
    get_user_by_email,
    verify_password,
)
from app.services.service_center_service import (
    ensure_demo_centers,
    fetch_centers_by_city,
    normalize_city,
)
from app.services.wheel_catalog_service import filesystem_path, list_wheels, public_url

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")
GOOGLE_MAPS_API_KEY = (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()
UPLOADS_DIR = PROJECT_ROOT / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

jinja_env = Environment(
    loader=FileSystemLoader(str(BASE_DIR / "templates")),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        ensure_demo_centers(db)
        ensure_wheel_catalog(db)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="wrapvision_session",
    max_age=14 * 24 * 60 * 60,
    same_site="lax",
    https_only=False,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


async def _save_upload(upload: UploadFile, prefix: str) -> str:
    raw = await upload.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Пустой файл")
    ext = Path(upload.filename or "").suffix
    if not ext or len(ext) > 8:
        ext = ".jpg"
    name = f"{prefix}_{uuid.uuid4().hex[:12]}{ext}"
    dest = UPLOADS_DIR / name
    dest.write_bytes(raw)
    return name


def _html(request: Request, name: str, **ctx: Any) -> HTMLResponse:
    context = {"request": request, **ctx}
    html = jinja_env.get_template(name).render(context)
    return HTMLResponse(content=html)


def _tel_digits(phone: str | None) -> str:
    if not phone:
        return ""
    return (
        phone.strip()
        .replace(" ", "")
        .replace("(", "")
        .replace(")", "")
        .replace("-", "")
    )


def _map_points_for_template(service_centers: list[Any]) -> list[dict[str, Any]]:
    """Точки для Google Maps: только записи с валидными координатами."""
    out: list[dict[str, Any]] = []
    for sc in service_centers:
        if getattr(sc, "is_active", True) is False:
            continue
        lat = getattr(sc, "latitude", None)
        lng = getattr(sc, "longitude", None)
        if lat is None or lng is None:
            continue
        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except (TypeError, ValueError):
            continue
        phone = (sc.phone or "").strip()
        website = (sc.website or "").strip()
        out.append(
            {
                "id": sc.id,
                "name": sc.name,
                "lat": lat_f,
                "lng": lng_f,
                "address": (sc.address or "").strip(),
                "phone": phone,
                "website": website,
                "tel": _tel_digits(sc.phone),
            }
        )
    return out


def _fallback_map_center(city: str) -> tuple[float, float]:
    """Центр карты, если нет маркеров или для начального вида."""
    key = normalize_city(city).casefold()
    if not key or key in ("—", "-"):
        return 55.7558, 37.6173
    centers_map: dict[str, tuple[float, float]] = {
        "москва": (55.7558, 37.6173),
        "санкт-петербург": (59.9343, 30.3351),
        "казань": (55.7911, 49.1203),
        "екатеринбург": (56.8431, 60.6454),
        "новосибирск": (55.0084, 82.9357),
        "краснодар": (45.0355, 38.9753),
        "нижний новгород": (56.2965, 43.9361),
        "самара": (53.2001, 50.1500),
        "ростов-на-дону": (47.2357, 39.7015),
        "воронеж": (51.6720, 39.1843),
        "пермь": (58.0105, 56.2502),
        "красноярск": (56.0153, 92.8932),
    }
    return centers_map.get(key, (55.7558, 37.6173))


def _result_wheel_display(db: Session, p: Project) -> tuple[str | None, str]:
    """URL превью дисков и короткая подпись для мета (пусто если диски не использовались)."""
    if p.wheels_enabled is False:
        return None, ""
    wheels_on = bool(p.wheels_enabled) if p.wheels_enabled is not None else bool(
            p.wheel_upload_name or p.wheel_catalog_id
        )
    if not wheels_on:
        return None, ""
    src = (p.wheel_source or "").strip().lower()
    if src == "catalog" and p.wheel_catalog_id:
        wc = db.get(WheelCatalog, p.wheel_catalog_id)
        if wc:
            return public_url(wc), f"каталог — {wc.title}"
        return None, "каталог"
    if p.wheel_upload_name:
        return f"/uploads/{p.wheel_upload_name}", f"загрузка — {p.wheel_upload_name}"
    if p.wheel_reference_image_path:
        path = p.wheel_reference_image_path.strip()
        if path.startswith("/"):
            return path, "загрузка"
        if path.startswith("uploads/"):
            return "/" + path, f"загрузка — {path.split('/')[-1]}"
    return None, ""


def _result_page_response(
    request: Request,
    *,
    car_filename: str,
    wrap_filename: str,
    wheels_need: bool,
    wheel_filename: str | None,
    result_image_url: str,
    user_city: str,
    service_centers: list[Any],
    wheel_ref_image_url: str | None = None,
    wheel_line: str = "",
    project_id: int | None = None,
    created_at: datetime | None = None,
) -> HTMLResponse:
    fb_lat, fb_lng = _fallback_map_center(user_city)
    partner_map_points = _map_points_for_template(service_centers)
    return _html(
        request,
        "result.html",
        car_filename=car_filename,
        wrap_filename=wrap_filename,
        wheels_need=wheels_need,
        wheel_filename=wheel_filename,
        result_image_url=result_image_url,
        user_city=user_city,
        service_centers=service_centers,
        wheel_ref_image_url=wheel_ref_image_url,
        wheel_line=wheel_line,
        project_id=project_id,
        created_at=created_at,
        current_user=_nav_user(request),
        maps_api_key=GOOGLE_MAPS_API_KEY,
        partner_map_points=partner_map_points,
        map_fallback_lat=fb_lat,
        map_fallback_lng=fb_lng,
    )


def _simple_error_page(title: str, message: str, status_code: int) -> HTMLResponse:
    safe_title = html.escape(title)
    safe_msg = html.escape(message)
    return HTMLResponse(
        content=(
            "<!DOCTYPE html><html lang='ru'><head><meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{safe_title}</title>"
            "<link rel='stylesheet' href='/static/css/style.css?v=28'></head>"
            "<body class='page ds-page'><main class='shell'><section class='card'>"
            f"<h1>{safe_title}</h1><p>{safe_msg}</p>"
            "<p><a class='link-back' href='/'>← На главную</a></p>"
            "</section></main></body></html>"
        ),
        status_code=status_code,
    )


def _session_user_id(request: Request) -> int | None:
    raw = request.session.get("user_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


_SHOWCASE_HOME_LIMIT = 3
_SHOWCASE_SESSION_IDS_KEY = "_showcase_random_ids_v1"
_SHOWCASE_SESSION_MARKER_KEY = "_showcase_random_marker_v1"


def _showcase_session_marker(request: Request) -> str:
    """При смене пользователя в сессии (вход выход регистрация) меняется маркер — подбираются новые 3 случайных кейса."""
    uid = _session_user_id(request)
    return f"user:{uid}" if uid is not None else "guest"


def _eligible_showcase_project_ids(session: Session) -> list[int]:
    ids = session.scalars(
        select(Project.id).where(Project.result_image_path.like("/uploads/generated_%"))
    ).all()
    return list(ids)


def _projects_by_ids_ordered(db: Session, ids: list[int]) -> list[Project]:
    if not ids:
        return []
    order = {pid: i for i, pid in enumerate(ids)}
    rows = list(db.scalars(select(Project).where(Project.id.in_(ids))).all())
    rows.sort(key=lambda p: order.get(p.id, 10**9))
    return rows


def _sample_showcase_ids(eligible: list[int]) -> list[int]:
    k = min(_SHOWCASE_HOME_LIMIT, len(eligible))
    if k == 0:
        return []
    if len(eligible) <= _SHOWCASE_HOME_LIMIT:
        shuffled = eligible[:]
        random.shuffle(shuffled)
        return shuffled
    return random.sample(eligible, k=k)


def _project_to_showcase_namespace(p: Project) -> SimpleNamespace:
    url = (p.result_image_path or "").strip()
    city = normalize_city(p.city or "") or "—"
    if p.wheels_enabled is not None:
        wheels_on = bool(p.wheels_enabled)
    else:
        wheels_on = bool(p.wheel_upload_name or p.wheel_catalog_id)
    has_wrap = bool(p.wrap_upload_name)
    if has_wrap and wheels_on:
        desc = "В запросе: смена плёнки по образцу и диски."
    elif has_wrap:
        desc = "В запросе: смена плёнки по образцу."
    elif wheels_on:
        desc = "В запросе: диски без смены плёнки."
    else:
        desc = "Превью без смены плёнки и дисков — авто на эталонном стенде."
    if p.created_at:
        desc += " " + p.created_at.strftime("%d.%m.%Y") + "."
    return SimpleNamespace(
        image_url=url,
        title=f"Готовое превью · {city}",
        description=desc,
    )


def _home_showcase_items(db: Session, request: Request) -> list[SimpleNamespace]:
    """Три случайные успешные генерации (/uploads/generated_*) среди всех пользователей; набор сохраняется в сессии и пересобирается при смене гость залогиненный пользователь."""
    marker = _showcase_session_marker(request)
    eligible = _eligible_showcase_project_ids(db)
    stored_marker = request.session.get(_SHOWCASE_SESSION_MARKER_KEY)
    raw_ids = request.session.get(_SHOWCASE_SESSION_IDS_KEY)

    picked: list[int] | None = None
    profile_changed = stored_marker != marker
    stale_ids = not isinstance(raw_ids, list) or (
        isinstance(raw_ids, list) and not raw_ids
    )

    if profile_changed or stale_ids:
        picked = _sample_showcase_ids(eligible)
        request.session[_SHOWCASE_SESSION_MARKER_KEY] = marker
        request.session[_SHOWCASE_SESSION_IDS_KEY] = picked
    else:
        cand = [int(x) for x in raw_ids]
        still = db.scalars(
            select(Project.id).where(
                Project.id.in_(cand),
                Project.result_image_path.like("/uploads/generated_%"),
            )
        ).all()
        if len(set(still)) != len(set(cand)):
            picked = _sample_showcase_ids(eligible)
            request.session[_SHOWCASE_SESSION_MARKER_KEY] = marker
            request.session[_SHOWCASE_SESSION_IDS_KEY] = picked
        else:
            picked = cand

    rows = _projects_by_ids_ordered(db, picked or [])
    return [
        _project_to_showcase_namespace(p)
        for p in rows
        if is_upload_api_generation_result(p.result_image_path)
    ]


def _nav_user(request: Request) -> SimpleNamespace | None:
    """Копия полей без привязки к закрытой сессии — шаблоны не трогают отсоединённый ORM."""
    uid = _session_user_id(request)
    if uid is None:
        return None
    with SessionLocal() as db:
        row = db.get(User, uid)
        if row is None:
            return None
        return SimpleNamespace(
            id=row.id,
            name=row.name,
            email=row.email,
            city=(row.city or ""),
        )


@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return _html(
        request,
        "register.html",
        current_user=_nav_user(request),
        error=None,
    )


@app.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    city: str = Form(...),
):
    name_s = name.strip()
    email_s = email.strip()
    city_norm = normalize_city(city)
    err: str | None = None
    if len(name_s) < 1:
        err = "Укажите имя"
    elif "@" not in email_s or "." not in email_s.split("@")[-1]:
        err = "Укажите корректный email"
    elif len(password) < 6:
        err = "Пароль не короче 6 символов"
    elif not city_norm:
        err = "Укажите город"
    if err:
        return _html(
            request,
            "register.html",
            current_user=_nav_user(request),
            error=err,
            form_name=name_s,
            form_email=email_s,
            form_city=city.strip(),
        )

    with SessionLocal() as db:
        if get_user_by_email(db, email_s) is not None:
            return _html(
                request,
                "register.html",
                current_user=_nav_user(request),
                error="Пользователь с таким email уже зарегистрирован",
                form_name=name_s,
                form_email=email_s,
                form_city=city.strip(),
            )
        try:
            user = create_user(
                db,
                name=name_s,
                email=email_s,
                password=password,
                city=city_norm,
            )
            db.commit()
        except IntegrityError:
            db.rollback()
            return _html(
                request,
                "register.html",
                current_user=_nav_user(request),
                error="Пользователь с таким email уже зарегистрирован",
                form_name=name_s,
                form_email=email_s,
                form_city=city.strip(),
            )

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_get(
    request: Request,
    next_url: str = Query("/", alias="next"),
):
    return _html(
        request,
        "login.html",
        current_user=_nav_user(request),
        error=None,
        next_url=next_url if next_url.startswith("/") else "/",
    )


@app.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    next_url = next.strip() or "/"
    if not next_url.startswith("/"):
        next_url = "/"

    with SessionLocal() as db:
        u = get_user_by_email(db, email)
        if u is None or not verify_password(password, u.password_hash):
            return _html(
                request,
                "login.html",
                current_user=_nav_user(request),
                error="Неверный email или пароль",
                next_url=next_url,
                form_email=email.strip(),
            )

    request.session["user_id"] = u.id
    return RedirectResponse(url=next_url, status_code=303)


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@app.get("/my/generations", response_class=HTMLResponse)
async def my_generations(request: Request):
    uid = _session_user_id(request)
    if uid is None:
        nxt = quote("/my/generations", safe="")
        return RedirectResponse(url=f"/login?next={nxt}", status_code=303)

    with SessionLocal() as db:
        user_row = db.get(User, uid)
        if user_row is None:
            request.session.clear()
            return RedirectResponse(url="/login", status_code=303)
        projects = list(
            db.scalars(
                select(Project)
                .where(Project.user_id == uid)
                .order_by(Project.created_at.desc())
            )
        )
        current_user = SimpleNamespace(
            id=user_row.id, name=user_row.name, email=user_row.email
        )
        project_views = [
            SimpleNamespace(
                id=p.id,
                created_at=p.created_at,
                city=p.city,
                result_image_path=p.result_image_path,
            )
            for p in projects
        ]

    return _html(
        request,
        "my_generations.html",
        current_user=current_user,
        projects=project_views,
    )


@app.get("/result/{project_id}", response_class=HTMLResponse)
async def result_by_project(request: Request, project_id: int):
    uid = _session_user_id(request)
    if uid is None:
        nxt = quote(f"/result/{project_id}", safe="")
        return RedirectResponse(url=f"/login?next={nxt}", status_code=303)

    with SessionLocal() as db:
        p = db.get(Project, project_id)
        if p is None or p.user_id != uid:
            raise HTTPException(status_code=404, detail="Генерация не найдена")
        city_key = p.city or ""
        service_centers_list = fetch_centers_by_city(db, city_key)
        car_fn = p.car_upload_name or ""
        wrap_fn = p.wrap_upload_name or ""
        wheel_fn = p.wheel_upload_name
        if p.wheels_enabled is not None:
            wheels_need = bool(p.wheels_enabled)
        else:
            wheels_need = bool(wheel_fn or p.wheel_catalog_id)
        wheel_ref_url, wheel_line = _result_wheel_display(db, p)
        result_url = p.result_image_path or RESULT_IMAGE_URL

    return _result_page_response(
        request,
        car_filename=car_fn,
        wrap_filename=wrap_fn,
        wheels_need=wheels_need,
        wheel_filename=wheel_fn if wheel_fn else None,
        result_image_url=result_url,
        user_city=city_key or "—",
        service_centers=service_centers_list,
        wheel_ref_image_url=wheel_ref_url,
        wheel_line=wheel_line,
        project_id=p.id,
        created_at=p.created_at,
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    uid = _session_user_id(request)
    if uid is None:
        nxt = quote("/", safe="")
        return RedirectResponse(url=f"/login?next={nxt}", status_code=303)
    with SessionLocal() as db:
        wheel_rows = list_wheels(db)
        showcase_items = _home_showcase_items(db, request)
    wheel_catalog_items = [
        SimpleNamespace(id=w.id, title=w.title, img_url=public_url(w))
        for w in wheel_rows
    ]
    return _html(
        request,
        "index.html",
        stand_reference_url="/static/img/stand_reference.jpg",
        current_user=_nav_user(request),
        wheel_catalog_items=wheel_catalog_items,
        showcase_items=showcase_items,
    )


@app.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    photo: UploadFile = File(...),
    wrap_needed: str = Form("yes"),
    wrap_sample: UploadFile | None = File(None),
    wheels_needed: str = Form(...),
    wheel_image: UploadFile | None = File(None),
    wheel_source: str = Form("catalog"),
    wheel_catalog_id: str = Form(""),
    city: str = Form(...),
):
    city_norm = normalize_city(city)
    if not city_norm:
        raise HTTPException(status_code=400, detail="Укажите город")

    mode_norm = GenerationMode.standard.value

    wn = wrap_needed.strip().lower()
    if wn not in ("yes", "no"):
        raise HTTPException(
            status_code=400,
            detail="Укажите, нужна ли плёнка: выберите «Да» или «Нет»",
        )
    wrap_need = wn == "yes"

    wh = wheels_needed.strip().lower()
    if wh not in ("yes", "no"):
        raise HTTPException(
            status_code=400,
            detail="Укажите, нужны ли диски: выберите «Да» или «Нет»",
        )
    wheels_need = wh == "yes"

    if not wrap_need and not wheels_need:
        raise HTTPException(
            status_code=400,
            detail="Выберите хотя бы одно: смену плёнки или смену дисков. "
            "Если ничего не меняем, смысла в генерации нет — отметьте «Да» там, что хотите изменить.",
        )

    car_filename = await _save_upload(photo, "car")
    if wrap_need:
        if wrap_sample is None or not (wrap_sample.filename or "").strip():
            raise HTTPException(
                status_code=400,
                detail="Загрузите фото образца плёнки",
            )
        wrap_filename = await _save_upload(wrap_sample, "wrap")
    else:
        wrap_filename = None

    wheel_filename: str | None = None
    wheel_catalog_pk: int | None = None
    ws_norm = (wheel_source or "catalog").strip().lower()
    if wheels_need:
        if ws_norm not in ("catalog", "upload"):
            raise HTTPException(
                status_code=400,
                detail="Источник дисков: каталог или загрузка",
            )
        if ws_norm == "catalog":
            raw_id = (wheel_catalog_id or "").strip()
            if not raw_id:
                raise HTTPException(
                    status_code=400,
                    detail="Выберите диск из каталога",
                )
            try:
                wheel_catalog_pk = int(raw_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Некорректный выбор каталога",
                ) from exc
            with SessionLocal() as db:
                wpath = filesystem_path(db, wheel_catalog_pk)
            if wpath is None:
                raise HTTPException(
                    status_code=400,
                    detail="Запись каталога дисков не найдена",
                )
            wheel_path_fs: Path | None = wpath
        else:
            if wheel_image is None or not (wheel_image.filename or "").strip():
                raise HTTPException(
                    status_code=400,
                    detail="Загрузите фото дисков или выберите вариант из каталога",
                )
            wheel_filename = await _save_upload(wheel_image, "wheel")
            wheel_path_fs = UPLOADS_DIR / wheel_filename
            wheel_catalog_pk = None
    else:
        wheel_path_fs = None

    car_path = UPLOADS_DIR / car_filename
    wrap_path = (UPLOADS_DIR / wrap_filename) if wrap_filename else None
    wheel_path = wheel_path_fs

    try:
        ordered_paths = build_ordered_image_paths(
            car_image_path=car_path,
            wrap_reference_path=wrap_path,
            wheel_reference_path=wheel_path,
            wrap_needed=wrap_need,
            wheels_needed=wheels_need,
        )
        final_prompt = build_final_prompt(
            wrap_needed=wrap_need,
            wheels_needed=wheels_need,
            ordered_image_paths=ordered_paths,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_uid = _session_user_id(request)

    with SessionLocal() as db:
        user_row: User | None = db.get(User, session_uid) if session_uid else None
        if user_row is not None:
            client = get_or_create_client_for_user(db, user_row)
            project_user_id = user_row.id
        else:
            client = db.scalars(select(Client).limit(1)).first()
            if client is None:
                client = Client(name="MVP Guest")
                db.add(client)
                db.flush()
            project_user_id = None

        access_val = AccessStatus.locked.value
        idea_db = None

        w_src = ws_norm if wheels_need else None
        w_cat = wheel_catalog_pk if wheels_need and ws_norm == "catalog" else None
        w_ref_path = (
            f"uploads/{wheel_filename}"
            if wheels_need and ws_norm == "upload" and wheel_filename
            else None
        )
        proj = Project(
            client_id=client.id,
            user_id=project_user_id,
            service_center_id=None,
            generation_mode=mode_norm,
            idea_prompt=idea_db,
            final_prompt=final_prompt,
            city=city_norm,
            access_status=access_val,
            wheels_enabled=wheels_need,
            wheel_source=w_src,
            wheel_catalog_id=w_cat,
            wheel_reference_image_path=w_ref_path,
            wheel_upload_name=wheel_filename
            if wheels_need and ws_norm == "upload"
            else None,
        )
        db.add(proj)
        db.flush()
        project_id = proj.id
        db.commit()
        service_centers_list = fetch_centers_by_city(db, city_norm)

    gen_in = GenerationInput(
        ordered_image_paths=tuple(ordered_paths),
        wheels_enabled=wheels_need,
        final_prompt=final_prompt,
    )
    try:
        generated_result_path = generate_result(gen_in)
    except DemoResultMissingError as exc:
        msg = html.escape(exc.args[0] if exc.args else str(exc))
        return HTMLResponse(
            content=(
                "<!DOCTYPE html><html lang='ru'><head><meta charset='UTF-8'>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'>"
                "<title>Ошибка</title>"
                "<link rel='stylesheet' href='/static/css/style.css?v=28'></head>"
                "<body class='page ds-page'><main class='shell'><section class='card'>"
                "<h1 class='page-title'>Нет демо-изображения результата</h1>"
                f"<p class='lead'>{msg}</p>"
                "<p><a class='link-back' href='/'>← На главную</a></p>"
                "</section></main></body></html>"
            ),
            status_code=503,
        )

    result_image_url = result_path_to_url(generated_result_path)

    project_created_at: datetime | None = None
    with SessionLocal() as db:
        row = db.get(Project, project_id)
        if row is not None:
            row.result_image_path = result_image_url
            row.car_upload_name = car_filename
            row.wrap_upload_name = wrap_filename
            db.commit()
            db.refresh(row)
            project_created_at = row.created_at

    wheel_ref_url: str | None = None
    wheel_line_out = ""
    if wheels_need:
        if ws_norm == "catalog" and wheel_catalog_pk is not None:
            with SessionLocal() as db:
                wc = db.get(WheelCatalog, wheel_catalog_pk)
                if wc:
                    wheel_ref_url = public_url(wc)
                    wheel_line_out = f"каталог — {wc.title}"
        elif wheel_filename:
            wheel_ref_url = f"/uploads/{wheel_filename}"
            wheel_line_out = f"загрузка — {wheel_filename}"

    return _result_page_response(
        request,
        car_filename=car_filename,
        wrap_filename=wrap_filename or "",
        wheels_need=wheels_need,
        wheel_filename=wheel_filename,
        result_image_url=result_image_url,
        user_city=city_norm,
        service_centers=service_centers_list,
        wheel_ref_image_url=wheel_ref_url,
        wheel_line=wheel_line_out,
        project_id=project_id,
        created_at=project_created_at,
    )
