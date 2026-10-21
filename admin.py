# -*- coding: utf-8 -*-
"""
admin.py — административная панель сайта «Ехидные крестики».

Здесь живут все страницы админки:

    /admin/login          — вход
    /admin/logout         — выход
    /admin                — главная (сводка)
    /admin/patterns       — каталог схем (таблица со всеми действиями)
    /admin/patterns/new   — добавление схемы
    /admin/patterns/<id>/edit — редактирование схемы
    /admin/patterns/<id>/preview — предпросмотр (в том числе черновика)
    /admin/categories     — категории
    /admin/settings       — настройки сайта
    /admin/backups        — резервные копии базы

Все страницы, кроме входа, закрыты: без авторизации открыть их нельзя.
Каждая форма защищена от CSRF (см. security.py).
"""

import os
from datetime import datetime

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, send_file,
    session, url_for,
)

import config
import database
import security
from security import UploadError

# Blueprint — это «набор страниц». Мы подключаем его в app.py.
admin = Blueprint("admin", __name__, url_prefix="/admin")


# ==========================================================================
# ПРОВЕРКА ДОСТУПА
# ==========================================================================

def current_admin():
    """
    Возвращает данные вошедшего администратора или None.
    Читаем id из сессии (её подписывает Flask секретным ключом,
    поэтому подделать сессию нельзя).
    """
    admin_id = session.get("admin_id")
    if not admin_id:
        return None
    user = database.get_admin()
    if user is None or user["id"] != admin_id:
        return None
    return user


def login_required(view):
    """
    «Обёртка» для маршрутов: пропускает дальше только вошедшего
    администратора. Остальных отправляет на страницу входа.
    """
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_admin() is None:
            # Запоминаем, куда администратор хотел попасть,
            # чтобы после входа вернуть его на нужную страницу
            session["next_url"] = request.full_path if request.query_string else request.path
            flash("Сначала войдите в панель.", "warning")
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)

    return wrapped


# ==========================================================================
# CSRF: защита форм
# ==========================================================================

def get_csrf_token():
    """
    Возвращает токен для формы. Если его ещё нет в сессии — создаёт.
    Токен добавляется в каждую форму скрытым полем.
    """
    if "csrf_token" not in session:
        session["csrf_token"] = security.make_csrf_token()
    return session["csrf_token"]


def check_csrf():
    """
    Проверяет токен из отправленной формы.
    Если он неверный — прерываем работу (403): значит, форму отправил
    чужой сайт или кто-то без прав.
    """
    expected = session.get("csrf_token")
    received = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not security.tokens_match(expected, received):
        abort(403, description="Недействительный CSRF-токен. Обновите страницу и попробуйте снова.")


# ==========================================================================
# ОБЩИЕ ДАННЫЕ ДЛЯ ШАБЛОНОВ АДМИНКИ
# ==========================================================================

# Маленькие картинки для меню. Нарисованы простыми линиями (SVG),
# поэтому не требуют отдельных файлов и остаются чёткими на любом экране.
ICONS = {
    "home": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10.5 12 4l8 6.5"/><path d="M6 10v9h12v-9"/></svg>',
    "grid": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/></svg>',
    "plus": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 8.5v7M8.5 12h7"/></svg>',
    "tags": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M4 4h7l9 9-7 7-9-9z"/><circle cx="8" cy="8" r="1.4" fill="currentColor" stroke="none"/></svg>',
    "settings": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><circle cx="12" cy="12" r="3.2"/><path d="M12 3.5v2.2M12 18.3v2.2M4.6 7.8l1.9 1.1M17.5 15.1l1.9 1.1M4.6 16.2l1.9-1.1M17.5 8.9l1.9-1.1"/></svg>',
    "shield": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 3.5 5 6v6c0 4 3 6.8 7 8.5 4-1.7 7-4.5 7-8.5V6z"/><path d="m9 12 2.2 2.2L15.5 10"/></svg>',
    "eye": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/></svg>',
    "users": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.2"/><path d="M3.5 19c.8-3 3-4.6 5.5-4.6S13.7 16 14.5 19"/><path d="M16 5.6a3 3 0 0 1 0 5.8M17.5 19c-.3-1.6-1-3-2-4"/></svg>',
    "library": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h5v14H4zM10.5 5h4v14h-4z"/><path d="M16.5 6.2l3.2.9-2.4 12.4-3.2-.9"/></svg>',
    "photos": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4.5" width="18" height="15" rx="2"/><circle cx="8.5" cy="9.5" r="1.6" fill="currentColor" stroke="none"/><path d="M4.5 17.5 9 12l3 3 2.5-2.5 5 5"/></svg>',
    "star": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M12 3.5 14.6 9l6 .7-4.4 4.1 1.2 5.9L12 16.9 6.6 19.7l1.2-5.9L3.4 9.7 9.4 9z"/></svg>',
    "home-plus": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10.5 12 4l8 6.5"/><path d="M6 10v9h12v-9"/><path d="M12 12.5v4M10 14.5h4"/></svg>',
}


def icon_svg(name):
    """Возвращает картинку для меню по её имени."""
    from markupsafe import Markup
    return Markup(ICONS.get(name, ""))


@admin.context_processor
def admin_globals():
    """Значения, доступные во всех шаблонах админки."""
    return {
        "admin_user": current_admin(),
        "csrf_token": get_csrf_token(),
        "icon_svg": icon_svg,
        "admin_nav": [
            ("admin.dashboard", "Главная", "home"),
            ("admin.patterns", "Каталог схем", "grid"),
            ("admin.pattern_new", "Добавить схему", "plus"),
            ("admin.categories", "Категории", "tags"),
            ("admin.users", "Покупатели", "users"),
            ("admin.entitlements", "Библиотека и права", "library"),
            ("admin.projects", "Отшивы покупателей", "photos"),
            ("admin.reviews", "Отзывы", "star"),
            ("admin.home_settings", "Главная страница", "home-plus"),
            ("admin.settings", "Настройки сайта", "settings"),
        ],
        # Счётчики того, что ждёт проверки — показываем в меню красной цифрой
        "pending_counts": {
            "projects": database.count_projects_by_status().get("pending", 0),
            "reviews": database.count_reviews_by_status().get("pending", 0),
        },
        "current_year": datetime.now().year,
        "brand_name": database.get_setting("site_name", config.BRAND_NAME),
        "config": config,
    }


# ==========================================================================
# ВХОД И ВЫХОД
# ==========================================================================

@admin.route("/login", methods=["GET", "POST"])
def login():
    """Страница входа. Проверяет логин, пароль и число попыток."""
    if current_admin() is not None:
        return redirect(url_for("admin.dashboard"))

    # Если админ ещё не настроен — честно подсказываем, что делать
    if database.count_admins() == 0:
        return render_template("admin/not_configured.html"), 200

    errors = {}
    username = ""

    if request.method == "POST":
        check_csrf()

        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        ip = request.remote_addr or ""

        # --- Проверка 1: не заблокирован ли вход ---
        failed = database.recent_failed_attempts(
            ip, config.LOGIN_ATTEMPT_WINDOW_MINUTES
        )
        if security.login_is_blocked(failed):
            errors["general"] = (
                f"Слишком много неудачных попыток входа. "
                f"Подождите {config.LOGIN_ATTEMPT_WINDOW_MINUTES} минут "
                "и попробуйте снова."
            )
        elif not username:
            errors["username"] = "Введите логин."
        elif not password:
            errors["password"] = "Введите пароль."
        else:
            # --- Проверка 2: логин и пароль ---
            user = database.get_admin(username)
            if user and security.verify_password(user["password_hash"], password):
                # Успех!
                database.add_login_attempt(username, ip, success=True)
                database.clear_login_attempts(ip)

                # Защита сессии: очищаем старые данные и выдаём новый id
                session.clear()
                session["admin_id"] = user["id"]
                session["admin_username"] = user["username"]
                session.permanent = True

                flash(f"Здравствуйте, {user['username']}! Вы вошли в панель.", "success")

                # Возвращаем туда, куда администратор шёл изначально
                next_url = session.pop("next_url", None)
                if next_url and next_url.startswith("/admin"):
                    return redirect(next_url)
                return redirect(url_for("admin.dashboard"))

            # Неудача: одинаковое сообщение и для чужого логина, и для
            # неверного пароля — так злоумышленник не узнает, что логин верный
            database.add_login_attempt(username, ip, success=False)
            failed = database.recent_failed_attempts(
                ip, config.LOGIN_ATTEMPT_WINDOW_MINUTES
            )
            left = security.attempts_left(failed)
            message = "Неверный логин или пароль."
            if left:
                message += f" Осталось попыток: {left}."
            errors["general"] = message

    return render_template(
        "admin/login.html",
        errors=errors,
        username=username,
        max_attempts=config.LOGIN_MAX_ATTEMPTS,
    )


@admin.route("/logout", methods=["POST"])
@login_required
def logout():
    """Выход из панели. Очищает сессию и возвращает на страницу входа."""
    check_csrf()
    session.clear()
    flash("Вы вышли из административной панели. Сессия закрыта.", "success")
    return redirect(url_for("admin.login"))


# ==========================================================================
# ГЛАВНАЯ (СВОДКА)
# ==========================================================================

@admin.route("/")
@login_required
def dashboard():
    """Сводка: сколько схем, черновиков, категорий и последние изменения."""
    status = database.count_by_status()
    recent = database.list_patterns(sort="updated_desc")[:5]
    return render_template(
        "admin/dashboard.html",
        total=database.count_patterns(),
        published=status["published"],
        drafts=status["draft"],
        categories_total=len(database.list_categories()),
        recent=recent,
        backups=database.list_backups()[:3],
        # Новые разделы: покупатели, библиотека, отшивы, отзывы
        users_total=database.count_users(),
        orders_total=database.count_orders(),
        projects_status=database.count_projects_by_status(),
        reviews_status=database.count_reviews_by_status(),
        pending_projects=database.list_projects(status="pending", limit=5),
        pending_reviews=database.list_reviews(status="pending", limit=5),
    )


# ==========================================================================
# КАТАЛОГ СХЕМ
# ==========================================================================

@admin.route("/patterns")
@login_required
def patterns():
    """
    Таблица всех схем: миниатюра, название, категория, цена, статус,
    дата изменения и действия.

    Поддерживает поиск по названию, фильтры по статусу и категории,
    сортировку и просмотр мягко удалённых записей.
    """
    search = (request.args.get("search") or "").strip()
    status = request.args.get("status") or ""
    category_id = request.args.get("category") or ""
    sort = request.args.get("sort") or "updated_desc"
    show_deleted = request.args.get("deleted") == "1"

    category_id = int(category_id) if category_id.isdigit() else None

    return render_template(
        "admin/patterns.html",
        patterns=database.list_patterns(
            search=search,
            status=status,
            category_id=category_id,
            sort=sort,
            include_deleted=show_deleted,
        ),
        categories=database.list_categories(),
        search=search,
        status=status,
        category_id=category_id,
        sort=sort,
        show_deleted=show_deleted,
    )


# ==========================================================================
# ФОРМА СХЕМЫ (ДОБАВЛЕНИЕ И РЕДАКТИРОВАНИЕ)
# ==========================================================================

# Значения, которые поля формы могут принимать по умолчанию
EMPTY_PATTERN = {
    "id": None,
    "slug": "",
    "title": "",
    "description": "",
    "full_description": "",
    "price": "",
    "currency": "RUB",
    "category_id": None,
    "width": "",
    "height": "",
    "colors": "",
    "fabric": "",
    "fabric_count": "",
    "finished_size": "",
    "difficulty": "",
    "main_image": "",
    "preview_10x10": "",
    "is_published": False,
    "gallery": [],
}


def _read_form(pattern_id=None):
    """
    Читает данные из формы и проверяет их.
    Возвращает (данные, изображения, ошибки).

    Если какие-то поля заполнены неверно — ошибки не пустые, и мы
    показываем форму снова, ничего не сохраняя.
    """
    form = request.form
    errors = {}

    title = (form.get("title") or "").strip()
    if not title:
        errors["title"] = "Укажите название схемы."

    description = (form.get("description") or "").strip()
    full_description = (form.get("full_description") or "").strip()

    # --- Цена ---
    price_raw = (form.get("price") or "").strip().replace(",", ".")
    price = 0.0
    if not price_raw:
        errors["price"] = "Укажите цену в рублях."
    else:
        try:
            price = float(price_raw)
            if price < 0:
                errors["price"] = "Цена не может быть отрицательной."
        except ValueError:
            errors["price"] = "Цена должна быть числом, например 350."

    # --- Адрес страницы (slug) ---
    slug = (form.get("slug") or "").strip().lower()
    if not slug:
        slug = database.unique_slug(title or "shema", exclude_id=pattern_id)
    elif not _slug_is_valid(slug):
        errors["slug"] = "Адрес может содержать только латинские буквы, цифры и дефисы."
    elif database.slug_exists(slug, exclude_id=pattern_id):
        errors["slug"] = "Такой адрес уже занят другой схемой. Измените его."

    # --- Категория ---
    category_raw = form.get("category_id") or ""
    category_id = int(category_raw) if category_raw.isdigit() else None

    # --- Числовые характеристики (необязательные) ---
    width = _optional_int(form.get("width"), "width", "Ширина", errors)
    height = _optional_int(form.get("height"), "height", "Высота", errors)
    colors = _optional_int(form.get("colors"), "colors", "Количество цветов", errors)
    fabric_count = _optional_int(form.get("fabric_count"), "fabric_count", "Каунт канвы", errors)

    data = {
        "slug": slug,
        "title": title,
        "description": description,
        "full_description": full_description,
        "price": price,
        "currency": "RUB",
        "category_id": category_id,
        "width": width,
        "height": height,
        "colors": colors,
        "fabric": (form.get("fabric") or "").strip(),
        "fabric_count": fabric_count,
        # Размер готовой работы автор пишет сам: без каунта ткани
        # посчитать сантиметры нельзя, а выдумывать их неправильно.
        "finished_size": (form.get("finished_size") or "").strip(),
        "difficulty": (form.get("difficulty") or "").strip(),
    }

    # --- Главное изображение ---
    main_image = (form.get("main_image_existing") or "").strip()
    upload = request.files.get("main_image")
    if upload and upload.filename:
        try:
            new_path = security.save_upload(upload, "uploads", prefix=slug or "shema")
            # Старый файл удаляем только если он лежал в папке загрузок
            security.delete_upload(main_image)
            main_image = new_path
        except UploadError as error:
            errors["main_image"] = str(error)
    elif form.get("remove_main_image") == "1":
        security.delete_upload(main_image)
        main_image = ""
    data["main_image"] = main_image

    # --- Фрагмент схемы 10×10 (загружается и хранится отдельно,
    #     автоматически из основной картинки не создаётся) ---
    preview = (form.get("preview_existing") or "").strip()
    preview_upload = request.files.get("preview_10x10")
    if preview_upload and preview_upload.filename:
        try:
            new_preview = security.save_upload(
                preview_upload, "uploads", prefix=(slug or "shema") + "-10x10"
            )
            security.delete_upload(preview)
            preview = new_preview
        except UploadError as error:
            errors["preview_10x10"] = str(error)
    elif form.get("remove_preview") == "1":
        security.delete_upload(preview)
        preview = ""
    data["preview_10x10"] = preview

    # --- Галерея: уже загруженные фото + новые файлы ---
    images = [path for path in form.getlist("gallery_existing") if path]
    for upload in request.files.getlist("gallery_new"):
        if not upload or not upload.filename:
            continue
        try:
            images.append(
                security.save_upload(upload, "uploads", prefix=(slug or "shema") + "-foto")
            )
        except UploadError as error:
            errors["gallery"] = str(error)

    return data, images, errors


def _slug_is_valid(slug):
    """Адрес страницы: только латиница, цифры и дефисы."""
    import re
    return bool(re.fullmatch(r"[a-z0-9\-]+", slug))


def _optional_int(value, field, label, errors):
    """Читает необязательное целое число из формы."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        number = int(value)
        if number < 0:
            errors[field] = f"{label} не может быть отрицательным."
            return None
        return number
    except ValueError:
        errors[field] = f"{label} — это целое число, например 145."
        return None


@admin.route("/patterns/new", methods=["GET", "POST"])
@login_required
def pattern_new():
    """Добавление новой схемы."""
    values = dict(EMPTY_PATTERN)

    if request.method == "POST":
        check_csrf()
        data, images, errors = _read_form()

        if not errors:
            # Кнопка «Опубликовать» публикует сразу,
            # «Сохранить черновик» — оставляет неопубликованной
            publish = request.form.get("action") == "publish"
            # Удаляем пустые адреса картинок, чтобы не мусорить
            pattern_id = database.create_pattern(data, images=images, publish=publish)
            if publish:
                flash("Схема опубликована и уже видна в каталоге.", "success")
            else:
                flash("Черновик сохранён. Его видите только вы.", "success")
            return redirect(url_for("admin.pattern_edit", pattern_id=pattern_id))

        # Есть ошибки — показываем форму снова с введёнными данными
        values.update(data)
        values["gallery"] = images
        flash("Проверьте отмеченные поля.", "error")

    return render_template(
        "admin/pattern_form.html",
        p=values,
        categories=database.list_categories(),
        errors=locals().get("errors", {}),
        is_new=True,
    )


@admin.route("/patterns/<int:pattern_id>/edit", methods=["GET", "POST"])
@login_required
def pattern_edit(pattern_id):
    """Редактирование существующей схемы. Данные не теряются."""
    pattern = database.get_pattern(pattern_id)
    if pattern is None:
        abort(404)

    errors = {}

    if request.method == "POST":
        check_csrf()
        data, images, errors = _read_form(pattern_id=pattern_id)

        if not errors:
            publish = request.form.get("action") == "publish"
            if request.form.get("action") == "draft":
                publish = False
            else:
                # «Предпросмотр» уже сохранил черновик —
                # при обычном сохранении статус не меняем
                publish = pattern["is_published"] if request.form.get("action") == "preview" else publish

            database.update_pattern(pattern_id, data, images=images, publish=publish)

            if request.form.get("action") == "preview":
                flash("Изменения сохранены. Открываю предпросмотр.", "success")
                return redirect(url_for("admin.pattern_preview", pattern_id=pattern_id))

            if publish:
                flash("Схема опубликована.", "success")
            else:
                flash("Черновик сохранён.", "success")
            return redirect(url_for("admin.pattern_edit", pattern_id=pattern_id))

        flash("Проверьте отмеченные поля — изменения пока не сохранены.", "error")
        pattern = dict(pattern)
        pattern.update(data)
        pattern["gallery"] = images

    # Галерея для формы: берём из базы, если это первый показ страницы
    if "gallery" not in pattern:
        pattern = dict(pattern)
        pattern["gallery"] = database.get_pattern_images(pattern_id)

    return render_template(
        "admin/pattern_form.html",
        p=pattern,
        categories=database.list_categories(),
        errors=errors,
        is_new=False,
    )


@admin.route("/patterns/<int:pattern_id>/preview")
@login_required
def pattern_preview(pattern_id):
    """
    Предпросмотр схемы. Доступен только администратору —
    поэтому черновики можно спокойно посмотреть до публикации.
    """
    pattern = database.get_pattern(pattern_id)
    if pattern is None:
        abort(404)
    return render_template("admin/pattern_preview.html", p=pattern)


# ==========================================================================
# ДЕЙСТВИЯ НАД СХЕМОЙ
# ==========================================================================

@admin.route("/patterns/<int:pattern_id>/toggle", methods=["POST"])
@login_required
def pattern_toggle(pattern_id):
    """Публикует схему или снимает её с публикации."""
    check_csrf()
    pattern = database.get_pattern(pattern_id)
    if pattern is None:
        abort(404)

    if pattern["is_published"]:
        database.set_published(pattern_id, False)
        flash(f"Схема «{pattern['title']}» снята с публикации.", "success")
    else:
        database.set_published(pattern_id, True)
        flash(f"Схема «{pattern['title']}» опубликована.", "success")
    return redirect(request.form.get("back") or url_for("admin.patterns"))


@admin.route("/patterns/<int:pattern_id>/duplicate", methods=["POST"])
@login_required
def pattern_duplicate(pattern_id):
    """Создаёт копию схемы в виде черновика."""
    check_csrf()
    pattern = database.get_pattern(pattern_id)
    if pattern is None:
        abort(404)

    new_id = database.duplicate_pattern(pattern_id)
    flash(
        f"Создана копия схемы «{pattern['title']}» (черновик). "
        "Отредактируйте её и опубликуйте.",
        "success",
    )
    return redirect(url_for("admin.pattern_edit", pattern_id=new_id))


@admin.route("/patterns/<int:pattern_id>/delete", methods=["POST"])
@login_required
def pattern_delete(pattern_id):
    """
    Мягкое удаление: схема уходит в «корзину» и её можно вернуть.
    Ничего не удаляется безвозвратно.
    """
    check_csrf()
    pattern = database.get_pattern(pattern_id)
    if pattern is None:
        abort(404)

    # Защита от случайного удаления всего каталога
    if database.count_patterns() <= 1 and request.form.get("confirm_all") != "yes":
        flash(
            "Это последняя схема в каталоге. Чтобы удалить её, "
            "подтвердите действие повторно.",
            "error",
        )
        return redirect(url_for("admin.patterns"))

    database.soft_delete_pattern(pattern_id)
    flash(
        f"Схема «{pattern['title']}» перемещена в удалённые. "
        "Её можно восстановить на странице каталога.",
        "success",
    )
    return redirect(url_for("admin.patterns"))


@admin.route("/patterns/<int:pattern_id>/restore", methods=["POST"])
@login_required
def pattern_restore(pattern_id):
    """Возвращает схему из удалённых."""
    check_csrf()
    pattern = database.get_pattern(pattern_id)
    if pattern is None:
        abort(404)
    database.restore_pattern(pattern_id)
    flash(f"Схема «{pattern['title']}» восстановлена.", "success")
    return redirect(url_for("admin.patterns", deleted="1"))


# ==========================================================================
# КАТЕГОРИИ
# ==========================================================================

@admin.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    """Добавление, переименование, порядок и видимость категорий."""
    if request.method == "POST":
        check_csrf()
        action = request.form.get("action")

        if action == "add":
            name = (request.form.get("name") or "").strip()
            if not name:
                flash("Введите название категории.", "error")
            elif database.get_category_by_name(name):
                flash(f"Категория «{name}» уже существует.", "error")
            else:
                database.add_category(name)
                flash(f"Категория «{name}» добавлена.", "success")

        elif action == "rename":
            category_id = request.form.get("category_id", type=int)
            name = (request.form.get("name") or "").strip()
            if not category_id or not name:
                flash("Не удалось переименовать категорию.", "error")
            else:
                database.update_category(category_id, name=name)
                flash("Название категории изменено.", "success")

        elif action == "hide":
            category_id = request.form.get("category_id", type=int)
            hide = request.form.get("hide") == "1"
            if category_id:
                database.update_category(category_id, is_hidden=hide)
                flash(
                    "Категория скрыта от покупателей." if hide
                    else "Категория снова видна покупателям.",
                    "success",
                )

        elif action == "move":
            # Кнопки «выше» / «ниже» меняют порядок соседних категорий
            category_id = request.form.get("category_id", type=int)
            direction = request.form.get("direction")
            _move_category(category_id, direction)

        elif action == "delete":
            category_id = request.form.get("category_id", type=int)
            new_category = request.form.get("move_to", type=int)
            result = database.delete_category(category_id, move_to_category_id=new_category)
            if result["deleted"]:
                flash("Категория удалена. Её можно вернуть.", "success")
            else:
                flash(
                    f"В категории {result['linked']} схем. "
                    "Сначала выберите, куда их перенести, — "
                    "иначе схемы потеряют категорию.",
                    "error",
                )

        return redirect(url_for("admin.categories"))

    return render_template(
        "admin/categories.html",
        categories=database.list_categories(include_deleted=False),
        counts=database.category_counts(),
    )


def _move_category(category_id, direction):
    """Меняет порядок категории: поднимает её выше или опускает ниже."""
    if not category_id or direction not in ("up", "down"):
        return
    items = database.list_categories()
    index = next(
        (i for i, item in enumerate(items) if item["id"] == category_id), None
    )
    if index is None:
        return

    if direction == "up" and index > 0:
        items[index - 1], items[index] = items[index], items[index - 1]
    elif direction == "down" and index < len(items) - 1:
        items[index + 1], items[index] = items[index], items[index + 1]
    else:
        return

    database.reorder_categories([item["id"] for item in items])


@admin.route("/categories/<int:category_id>/restore", methods=["POST"])
@login_required
def category_restore(category_id):
    """Возвращает удалённую категорию."""
    check_csrf()
    database.restore_category(category_id)
    flash("Категория восстановлена.", "success")
    return redirect(url_for("admin.categories"))


# ==========================================================================
# НАСТРОЙКИ САЙТА
# ==========================================================================

@admin.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """
    Название сайта, подзаголовок, текст первого экрана, «О проекте»,
    логотип, ссылка ВКонтакте и контакты.

    Логотип только загружается. Сайт не рисует и не придумывает логотип сам.
    """
    errors = {}

    if request.method == "POST":
        check_csrf()

        values = {
            "site_name": (request.form.get("site_name") or "").strip(),
            "site_tagline": (request.form.get("site_tagline") or "").strip(),
            "slogan": (request.form.get("slogan") or "").strip(),
            "hero_title": (request.form.get("hero_title") or "").strip(),
            "hero_subtitle": (request.form.get("hero_subtitle") or "").strip(),
            "hero_button": (request.form.get("hero_button") or "").strip(),
            "catalog_title": (request.form.get("catalog_title") or "").strip(),
            "about_title": (request.form.get("about_title") or "").strip(),
            "about_text": (request.form.get("about_text") or "").strip(),
            "vk_url": (request.form.get("vk_url") or "").strip(),
            "contact_email": (request.form.get("contact_email") or "").strip(),
            "contact_phone": (request.form.get("contact_phone") or "").strip(),
            "contact_text": (request.form.get("contact_text") or "").strip(),
            "checkout_notice": (request.form.get("checkout_notice") or "").strip(),
        }

        if not values["site_name"]:
            errors["site_name"] = "Название сайта не может быть пустым."

        # Ссылки проверяем: они должны начинаться с http:// или https://
        for field, label in (("vk_url", "Ссылка ВКонтакте"),):
            link = values[field]
            if link and not link.startswith(("http://", "https://")):
                errors[field] = f"{label} должна начинаться с https://"

        if values["contact_email"] and "@" not in values["contact_email"]:
            errors["contact_email"] = "Проверьте адрес электронной почты."

        # --- Логотип ---
        logo = database.get_setting("logo")
        logo_upload = request.files.get("logo")
        remove_logo = request.form.get("remove_logo") == "1"

        if logo_upload and logo_upload.filename:
            try:
                logo = security.save_upload(logo_upload, "uploads", prefix="logo")
            except UploadError as error:
                errors["logo"] = str(error)
        elif remove_logo:
            security.delete_upload(logo)
            logo = ""

        if not errors:
            database.set_settings(values)
            database.set_setting("logo", logo)
            flash("Настройки сайта сохранены.", "success")
            return redirect(url_for("admin.settings"))

        flash("Проверьте отмеченные поля.", "error")

    return render_template(
        "admin/settings.html",
        settings=database.get_settings(),
        errors=errors,
    )


# ==========================================================================
# РЕЗЕРВНЫЕ КОПИИ
# ==========================================================================

@admin.route("/backups", methods=["GET", "POST"])
@login_required
def backups():
    """Список резервных копий базы и кнопка «создать копию сейчас»."""
    if request.method == "POST":
        check_csrf()
        path = database.backup_database()
        if path:
            flash("Резервная копия создана.", "success")
        else:
            flash("База данных пока пустая — копировать нечего.", "error")
        return redirect(url_for("admin.backups"))

    return render_template("admin/backups.html", backups=database.list_backups())


# ==========================================================================
# ПОКУПАТЕЛИ
# ==========================================================================

@admin.route("/users")
@login_required
def users():
    """Список зарегистрированных покупателей с поиском."""
    search = (request.args.get("q") or "").strip()
    return render_template(
        "admin/users.html",
        users=database.list_users(search=search),
        search=search,
    )


@admin.route("/users/<int:user_id>")
@login_required
def user_detail(user_id):
    """Карточка покупателя: библиотека, отшивы, отзывы, заказы."""
    user = database.get_user(user_id)
    if user is None:
        abort(404)
    return render_template(
        "admin/user_detail.html",
        user=user,
        library=database.list_user_library(user_id),
        orders=database.list_user_orders(user_id),
        projects=database.list_projects(user_id=user_id),
        reviews=database.list_user_reviews(user_id),
        all_patterns=database.list_patterns(sort="title_asc"),
        public_name=database.public_display_name(user),
    )


@admin.route("/users/<int:user_id>/block", methods=["POST"])
@login_required
def user_block(user_id):
    """Блокировка и разблокировка аккаунта покупателя."""
    check_csrf()
    user = database.get_user(user_id)
    if user is None:
        abort(404)
    database.set_user_blocked(user_id, not user["is_blocked"])
    flash(
        "Аккаунт заблокирован." if not user["is_blocked"] else "Аккаунт разблокирован.",
        "success",
    )
    return redirect(url_for("admin.user_detail", user_id=user_id))


@admin.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
def user_delete(user_id):
    """Мягкое удаление аккаунта (данные сохраняются, можно вернуть)."""
    check_csrf()
    if database.get_user(user_id) is None:
        abort(404)
    database.delete_user(user_id)
    flash("Аккаунт скрыт. При необходимости его можно восстановить.", "success")
    return redirect(url_for("admin.users"))


@admin.route("/users/<int:user_id>/restore", methods=["POST"])
@login_required
def user_restore(user_id):
    """Возвращает мягко удалённый аккаунт."""
    check_csrf()
    database.restore_user(user_id)
    flash("Аккаунт восстановлен.", "success")
    return redirect(url_for("admin.user_detail", user_id=user_id))


# ==========================================================================
# БИБЛИОТЕКА И ПРАВА ДОСТУПА
# ==========================================================================

@admin.route("/entitlements", methods=["GET", "POST"])
@login_required
def entitlements():
    """
    Права скачивания схем.

    Здесь же администратор вручную вносит прошлую покупку: выбирает
    покупателя, схемы и (необязательно) файлы. Право доступа выдаётся
    только отсюда — добавление схемы в корзину само по себе ничего
    не открывает.
    """
    errors = {}

    if request.method == "POST":
        check_csrf()
        action = request.form.get("action") or "grant"

        # --- Отозвать право ---
        if action == "revoke":
            user_id = request.form.get("user_id", type=int)
            pattern_id = request.form.get("pattern_id", type=int)
            if user_id and pattern_id:
                database.revoke_entitlement(user_id, pattern_id)
                admin_name = (current_admin() or {}).get("username", "")
                database.log_moderation(
                    "entitlement", pattern_id, "revoke", "Право отозвано", admin_name
                )
                flash("Право скачивания отозвано.", "success")
            return redirect(url_for("admin.entitlements"))

        # --- Выдать право + записать заказ ---
        user_id = request.form.get("user_id", type=int)
        pattern_ids = request.form.getlist("pattern_ids")
        note = (request.form.get("note") or "").strip()
        make_order = request.form.get("make_order") == "1"

        if not user_id or database.get_user(user_id) is None:
            errors["user_id"] = "Выберите покупателя."
        selected = []
        for raw in pattern_ids:
            try:
                pid = int(raw)
            except (TypeError, ValueError):
                continue
            pattern = database.get_pattern(pid)
            if pattern:
                selected.append(pattern)
        if not selected:
            errors["pattern_ids"] = "Выберите хотя бы одну схему."

        if errors:
            flash("Проверьте отмеченные поля.", "error")
        else:
            order_id = None
            order_number = ""
            if make_order:
                items = [
                    {"pattern_id": p["id"], "title": p["title"], "price": p["price"]}
                    for p in selected
                ]
                order_id, order_number = database.create_order(
                    user_id, items, note=note, source="manual"
                )

            for pattern in selected:
                database.grant_entitlement(
                    user_id, pattern["id"], order_id=order_id,
                    granted_by=(current_admin() or {}).get("username", "admin"),
                    note=note,
                )

            if order_number:
                flash(
                    f"Права выданы, заказ {order_number} внесён вручную.",
                    "success",
                )
            else:
                flash("Права скачивания выданы.", "success")
            return redirect(url_for("admin.entitlements"))

    search = (request.args.get("q") or "").strip()
    return render_template(
        "admin/entitlements.html",
        entitlements=database.list_entitlements(search=search),
        users=database.list_users(),
        patterns=database.list_patterns(sort="title_asc"),
        orders=database.list_orders(),
        search=search,
        errors=errors,
    )


@admin.route("/patterns/<int:pattern_id>/files", methods=["GET", "POST"])
@login_required
def pattern_files(pattern_id):
    """
    Цифровые файлы схемы (PDF, Saga, Paradise).

    Файлы физически лежат в папке protected/ (вне static/), поэтому
    скачать их по прямой ссылке нельзя: сервер отдаёт файл только
    покупателю с действующим правом доступа.
    """
    pattern = database.get_pattern(pattern_id)
    if pattern is None:
        abort(404)

    errors = {}
    if request.method == "POST":
        check_csrf()
        action = request.form.get("action") or "upload"

        if action == "delete":
            file_id = request.form.get("file_id", type=int)
            pattern_file = database.get_pattern_file(file_id)
            if pattern_file and pattern_file["pattern_id"] == pattern_id:
                # Сначала убираем запись, потом сам файл
                database.delete_pattern_file(file_id)
                path = os.path.join(config.PROTECTED_DIR, os.path.basename(pattern_file["stored_name"]))
                if os.path.isfile(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                flash("Файл удалён.", "success")
            return redirect(url_for("admin.pattern_files", pattern_id=pattern_id))

        if action == "toggle":
            file_id = request.form.get("file_id", type=int)
            pattern_file = database.get_pattern_file(file_id)
            if pattern_file and pattern_file["pattern_id"] == pattern_id:
                database.set_pattern_file_active(file_id, not pattern_file["is_active"])
                flash("Готово.", "success")
            return redirect(url_for("admin.pattern_files", pattern_id=pattern_id))

        # --- Загрузка нового файла ---
        format_name = (request.form.get("format") or "pdf").strip().lower()
        title = (request.form.get("title") or "").strip()
        upload = request.files.get("file")

        if format_name not in ("pdf", "saga", "paradise", "other"):
            errors["format"] = "Выберите формат файла."
        if not upload or not upload.filename:
            errors["file"] = "Выберите файл."

        if not errors:
            stored = security.safe_protected_name(upload.filename)
            os.makedirs(config.PROTECTED_DIR, exist_ok=True)
            full_path = os.path.join(config.PROTECTED_DIR, stored)
            # Защита от выхода за пределы папки
            if not os.path.abspath(full_path).startswith(os.path.abspath(config.PROTECTED_DIR)):
                errors["file"] = "Недопустимое имя файла."
            else:
                upload.save(full_path)
                size = os.path.getsize(full_path)
                database.add_pattern_file(
                    pattern_id=pattern_id,
                    format_name=format_name,
                    stored_name=stored,
                    title=title,
                    original_name=upload.filename,
                    size_bytes=size,
                )
                flash("Файл загружен и доступен покупателям с правом скачивания.", "success")
                return redirect(url_for("admin.pattern_files", pattern_id=pattern_id))

        flash("Проверьте отмеченные поля.", "error")

    return render_template(
        "admin/pattern_files.html",
        pattern=pattern,
        files=database.list_pattern_files(pattern_id),
        errors=errors,
    )


# ==========================================================================
# ОТШИВЫ ПОКУПАТЕЛЕЙ (МОДЕРАЦИЯ)
# ==========================================================================

@admin.route("/projects")
@login_required
def projects():
    """Все отшивы. По умолчанию показываем те, что ждут проверки."""
    status = request.args.get("status") or "pending"
    if status not in ("pending", "approved", "rejected", "hidden", "withdrawn", "all"):
        status = "pending"

    items = database.list_projects(status="" if status == "all" else status)
    # Для карточек нужны фотографии: оригиналы лежат в защищённой папке,
    # поэтому показываем их через отдельный админ-маршрут.
    return render_template(
        "admin/projects.html",
        projects=items,
        status=status,
        counts=database.count_projects_by_status(),
        moderation_log=database.list_moderation_actions("project", limit=40),
    )


@admin.route("/projects/<int:project_id>/photo/<int:index>")
@login_required
def project_photo(project_id, index):
    """
    Отдаёт фотографию отшива администратору (в том числе до публикации).

    Фотография может лежать в двух местах:
      * оригинал — в защищённой папке (до одобрения);
      * опубликованная копия — в static/images/projects/ (после одобрения).
    Публично оригиналы недоступны.
    """
    images = database.get_project_images(project_id)
    if index < 0 or index >= len(images):
        abort(404)

    stored_path = images[index]["path"]

    # Опубликованная копия — это относительный путь от static/
    if stored_path.startswith("images/"):
        public_root = os.path.abspath(config.STATIC_DIR)
        full_path = os.path.abspath(
            os.path.join(config.STATIC_DIR, stored_path.replace("/", os.sep))
        )
        if not full_path.startswith(public_root) or not os.path.isfile(full_path):
            abort(404)
        return send_file(full_path, max_age=0)

    # Оригинал — только имя файла внутри защищённой папки
    stored_name = os.path.basename(stored_path)
    full_path = os.path.join(config.PROJECT_UPLOAD_DIR, stored_name)
    if not os.path.isfile(full_path):
        abort(404)
    return send_file(full_path, max_age=0)


@admin.route("/projects/<int:project_id>/moderate", methods=["POST"])
@login_required
def project_moderate(project_id):
    """
    Одобрение, отклонение, скрытие и удаление отшива.

    При одобрении делаются оптимизированные копии фотографий для
    публичного показа. Оригиналы остаются в защищённой папке.
    """
    check_csrf()
    project = database.get_project(project_id)
    if project is None:
        abort(404)

    action = request.form.get("action") or ""
    reason = (request.form.get("reason") or "").strip()
    admin_name = (current_admin() or {}).get("username", "")

    if action == "approve":
        # Готовим публичные копии фотографий (только для оригиналов)
        images = database.get_project_images(project_id)
        for image in images:
            if image["path"].startswith("images/"):
                continue  # уже опубликовано
            public_path = security.publish_project_photo(image["path"])
            if public_path:
                database.update_project_image(image["id"], public_path)
        database.set_project_status(project_id, "approved", reason)
        database.set_project_show_on_home(project_id, True)
        database.log_moderation("project", project_id, "approve", reason, admin_name)
        flash("Отшив одобрен и опубликован.", "success")

    elif action == "reject":
        if not reason:
            flash("Укажите причину отклонения — автор должен её видеть.", "error")
            return redirect(url_for("admin.projects", status="pending"))
        database.set_project_status(project_id, "rejected", reason, show_on_home=False)
        database.log_moderation("project", project_id, "reject", reason, admin_name)
        flash("Отшив отклонён. Причина будет видна автору.", "success")

    elif action == "hide":
        database.set_project_status(project_id, "hidden", reason, show_on_home=False)
        database.log_moderation("project", project_id, "hide", reason, admin_name)
        flash("Отшив скрыт с сайта.", "success")

    elif action == "show":
        database.set_project_show_on_home(project_id, True)
        flash("Работа снова показывается на главной.", "success")

    elif action == "hide_home":
        database.set_project_show_on_home(project_id, False)
        flash("Работа убрана с главной страницы, но осталась в галерее.", "success")

    elif action == "delete":
        # Удаляем и оригиналы, и опубликованные копии
        for image in database.get_project_images(project_id):
            security.delete_protected_file(image["path"])
            security.delete_public_project_image(image["path"])
        database.delete_project(project_id)
        database.log_moderation("project", project_id, "delete", reason, admin_name)
        flash("Отшив удалён полностью.", "success")
        return redirect(url_for("admin.projects", status=request.form.get("back", "pending")))

    return redirect(url_for("admin.projects", status=request.form.get("back", "pending")))


# ==========================================================================
# ОТЗЫВЫ (МОДЕРАЦИЯ)
# ==========================================================================

@admin.route("/reviews")
@login_required
def reviews():
    """Все отзывы. По умолчанию — те, что ждут проверки."""
    status = request.args.get("status") or "pending"
    if status not in ("pending", "approved", "rejected", "hidden", "all"):
        status = "pending"
    return render_template(
        "admin/reviews.html",
        reviews=database.list_reviews(status="" if status == "all" else status),
        status=status,
        counts=database.count_reviews_by_status(),
        moderation_log=database.list_moderation_actions("review", limit=40),
    )


@admin.route("/reviews/<int:review_id>/moderate", methods=["POST"])
@login_required
def review_moderate(review_id):
    """
    Одобрение, отклонение, скрытие и удаление отзыва.

    Важно: отрицательная оценка сама по себе НЕ является причиной
    для отклонения. Отклоняем только за нарушение правил (спам,
    оскорбления, чужие данные, реклама), и причину видит автор.
    """
    check_csrf()
    review = database.get_review(review_id)
    if review is None:
        abort(404)

    action = request.form.get("action") or ""
    reason = (request.form.get("reason") or "").strip()
    admin_name = (current_admin() or {}).get("username", "")

    if action == "approve":
        database.set_review_status(review_id, "approved", reason)
        database.log_moderation("review", review_id, "approve", reason, admin_name)
        flash("Отзыв опубликован.", "success")

    elif action == "reject":
        if not reason:
            flash("Укажите причину — автор должен понимать, что не так.", "error")
            return redirect(url_for("admin.reviews", status="pending"))
        database.set_review_status(review_id, "rejected", reason)
        database.log_moderation("review", review_id, "reject", reason, admin_name)
        flash("Отзыв отклонён.", "success")

    elif action == "hide":
        database.set_review_status(review_id, "hidden", reason)
        database.log_moderation("review", review_id, "hide", reason, admin_name)
        flash("Отзыв скрыт.", "success")

    elif action == "delete":
        database.delete_review(review_id)
        database.log_moderation("review", review_id, "delete", reason, admin_name)
        flash("Отзыв удалён (например, как спам).", "success")
        return redirect(url_for("admin.reviews", status=request.form.get("back", "pending")))

    return redirect(url_for("admin.reviews", status=request.form.get("back", "pending")))


# ==========================================================================
# НАСТРОЙКИ ГЛАВНОЙ СТРАНИЦЫ
# ==========================================================================

@admin.route("/home", methods=["GET", "POST"])
@login_required
def home_settings():
    """
    Заголовки галереи и блока отзывов, количество элементов на главной
    и имена файлов фирменных изображений.
    """
    errors = {}

    if request.method == "POST":
        check_csrf()

        values = {
            "gallery_title": (request.form.get("gallery_title") or "").strip(),
            "gallery_subtitle": (request.form.get("gallery_subtitle") or "").strip(),
            "gallery_empty_message": (request.form.get("gallery_empty_message") or "").strip(),
            "reviews_title": (request.form.get("reviews_title") or "").strip(),
            "reviews_subtitle": (request.form.get("reviews_subtitle") or "").strip(),
            "reviews_empty_message": (request.form.get("reviews_empty_message") or "").strip(),
            "brand_avatar_caption": (request.form.get("brand_avatar_caption") or "").strip(),
            "brand_logo_file": (request.form.get("brand_logo_file") or "").strip(),
            "brand_avatar_file": (request.form.get("brand_avatar_file") or "").strip(),
        }

        # Количество элементов: целое число от 0 до 24
        for field, label, maximum in (
            ("gallery_home_count", "Работ на главной", 24),
            ("reviews_home_count", "Отзывов на главной", 12),
        ):
            raw = (request.form.get(field) or "").strip()
            try:
                number = int(raw)
            except (TypeError, ValueError):
                errors[field] = f"{label}: введите целое число."
                continue
            if number < 0 or number > maximum:
                errors[field] = f"{label}: допустимо от 0 до {maximum}."
            else:
                values[field] = str(number)

        # Имена файлов бренда: только имя, без пути
        for field, label in (
            ("brand_logo_file", "Файл логотипа"),
            ("brand_avatar_file", "Файл аватара"),
        ):
            name = values[field]
            if name and (os.path.basename(name) != name or "/" in name or "\\" in name):
                errors[field] = f"{label}: укажите только имя файла, без папок."

        if not errors:
            database.set_settings(values)
            flash("Настройки главной страницы сохранены.", "success")
            return redirect(url_for("admin.home_settings"))

        flash("Проверьте отмеченные поля.", "error")

    return render_template(
        "admin/home_settings.html",
        settings=database.get_settings(),
        errors=errors,
        logo_exists=config._brand_file_exists(
            database.get_setting("brand_logo_file") or config.BRAND_LOGO_FILE
        ),
        avatar_exists=config._brand_file_exists(
            database.get_setting("brand_avatar_file") or config.BRAND_AVATAR_FILE
        ),
        logo_url=config.find_logo_url(),
        avatar_url=config.find_avatar_url(),
    )
