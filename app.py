# -*- coding: utf-8 -*-
"""
app.py — главный файл сайта-каталога «Ехидные крестики».

Запуск:  python app.py
После запуска откройте в браузере:  http://127.0.0.1:5000

Что здесь происходит:

1) Flask — лёгкий веб-фреймворк на Python.
2) Публичные маршруты: главная, страница схемы, корзина, API, 404.
3) Административная панель подключается отдельно (файл admin.py)
   и живёт по адресам /admin/...
4) Данные каталога теперь хранятся в базе SQLite (data/catalog.db).
   Прежние JSON-файлы остались как резервная копия.

Важно: база данных НЕ пересоздаётся при каждом запуске. Функция
database.init_db() только создаёт недостающие таблицы и ничего не удаляет.
"""

import os
import re
from datetime import datetime, timedelta

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

import config
import database
# --------------------------------------------------------------------------
# Создание приложения. __name__ помогает Flask найти папки templates/static.
# --------------------------------------------------------------------------
app = Flask(__name__)

# --------------------------------------------------------------------------
# Настройки безопасности
# --------------------------------------------------------------------------
# Секретный ключ подписывает сессии (в том числе вход администратора).
# Он берётся из переменной окружения EK_SECRET_KEY — в коде его нет.
if config.SECRET_KEY:
    app.secret_key = config.SECRET_KEY
else:
    # Ключа нет — придумываем временный и честно предупреждаем.
    # Пользоваться так можно только для первого знакомства с сайтом.
    app.secret_key = os.urandom(32)
    print("\n" + "!" * 70)
    print("ВНИМАНИЕ: не задан секретный ключ EK_SECRET_KEY.")
    print("Сейчас использован временный ключ — после перезапуска сервера")
    print("администратору придётся войти в панель снова.")
    print("Чтобы задать постоянный ключ:")
    print('  Windows (cmd):        set EK_SECRET_KEY=длинная-случайная-строка')
    print('  Windows (PowerShell): $env:EK_SECRET_KEY="длинная-случайная-строка"')
    print('  macOS / Linux:        export EK_SECRET_KEY="длинная-случайная-строка"')
    print("!" * 70 + "\n")

# --- Безопасные настройки сессионной cookie ---
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,     # cookie недоступна из JavaScript
    SESSION_COOKIE_SAMESITE="Lax",    # защита от CSRF через переходы с других сайтов
    SESSION_COOKIE_SECURE=False,      # на локальном http; на хостинге поставьте True
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=config.SESSION_LIFETIME_MINUTES),
    MAX_CONTENT_LENGTH=config.MAX_UPLOAD_SIZE_MB * 1024 * 1024 * 2,
)

# Инициализация базы: создаём таблицы, если их ещё нет.
# Существующие данные при этом не трогаются.
database.init_db()

# Подключаем административную панель (все её страницы начинаются с /admin)
from admin import admin  # noqa: E402

app.register_blueprint(admin)

# Подключаем личные кабинеты покупателей (маршруты /register, /login, /account)
from users import login_manager, users as users_blueprint  # noqa: E402

login_manager.init_app(app)
app.register_blueprint(users_blueprint)

# Публичный блок галереи отшивов и отзывов живёт в отдельном файле,
# чтобы app.py не разрастался.
from public_content import public_content  # noqa: E402

app.register_blueprint(public_content)


# --------------------------------------------------------------------------
# Безопасный путь к изображению
# --------------------------------------------------------------------------
def _safe_image_path(path):
    """
    Проверяет, что путь к изображению безопасен и файл существует.

    Запрещены: абсолютные пути, «..», обратные слэши и внешние ссылки.
    Если проверка не прошла — возвращаем None, и сайт покажет заглушку.
    """
    if not path or not isinstance(path, str):
        return None
    path = path.strip()
    if path.startswith(("/", "\\", "http://", "https://", "file:")) or ".." in path:
        return None
    if "\\" in path or ":" in path:
        return None
    full = os.path.join(config.STATIC_DIR, path.replace("/", os.sep))
    if not os.path.isfile(full):
        return None
    return path


def image_or_placeholder(path):
    """Безопасный путь к изображению. Если файла нет — аккуратная заглушка."""
    return _safe_image_path(path) or "images/placeholders/no-image.svg"


# --------------------------------------------------------------------------
# Работа с данными из базы
# --------------------------------------------------------------------------

def get_active_patterns():
    """Опубликованные схемы — для каталога и API."""
    return database.list_published_patterns()


def get_pattern(slug):
    """Находит схему по адресу страницы. Или None."""
    return database.get_pattern_by_slug(slug)


def get_related(slug, count=3):
    """Другие опубликованные схемы — для блока «Возможно, вам понравится»."""
    others = [p for p in get_active_patterns() if p["slug"] != slug]
    return others[:count]


def visible_categories():
    """
    Категории для фильтра в каталоге: только не скрытые и не пустые.
    Показываем те, в которых есть хотя бы одна опубликованная схема.
    """
    used_ids = {p["category_id"] for p in get_active_patterns() if p["category_id"]}
    return [
        category for category in database.list_categories(include_hidden=False)
        if category["id"] in used_ids
    ]


def pattern_to_view(pattern):
    """
    Готовит схему для шаблона: безопасные пути картинок,
    галерея и размер готовой работы в сантиметрах (если известен каунт).
    """
    view = dict(pattern)
    main_image = pattern.get("main_image")
    view["image_url"] = image_or_placeholder(main_image)
    view["image_missing"] = _safe_image_path(main_image) is None
    view["preview_url"] = _safe_image_path(pattern.get("preview_10x10"))
    view["gallery_urls"] = [
        image for image in database.get_pattern_images(pattern["id"])
        if _safe_image_path(image)
    ]

    # Размер готовой работы считаем только если известен каунт ткани:
    # (количество крестиков / каунт) * 2.54 см. Иначе — не выдумываем.
    width = pattern.get("width")
    height = pattern.get("height")
    count = pattern.get("fabric_count")
    if width and height and count:
        view["finished_cm_width"] = round(width / count * 2.54, 1)
        view["finished_cm_height"] = round(height / count * 2.54, 1)
    else:
        view["finished_cm_width"] = None
        view["finished_cm_height"] = None

    # Размер в виде «145×115» — для шаблонов
    view["size_stitches"] = {"width": width, "height": height}
    return view


def pattern_public_data(pattern):
    """Публичные данные схемы для API и корзины (без внутренних полей)."""
    return {
        "id": pattern["id"],
        "slug": pattern["slug"],
        "title": pattern["title"],
        "description": pattern.get("description", ""),
        "price": pattern["price"],
        "currency": pattern.get("currency", "RUB"),
        "size_stitches": {
            "width": pattern.get("width"),
            "height": pattern.get("height"),
        },
        "colors": pattern.get("colors"),
        "category": pattern.get("category", ""),
        "difficulty": pattern.get("difficulty"),
        "image_url": "/static/" + image_or_placeholder(pattern.get("main_image")),
        "url": "/pattern/" + pattern["slug"],
    }


# --------------------------------------------------------------------------
# Общие данные для всех шаблонов: бренд, тексты, год в подвале
# --------------------------------------------------------------------------
@app.context_processor
def inject_globals():
    """
    Значения, доступные в каждом шаблоне сайта.
    Тексты берутся из настроек в базе — их можно менять прямо в админ-панели.
    """
    settings = database.get_settings()
    logo = settings.get("logo") or config.LOGO_URL or ""

    # Фирменные изображения: логотип и аватар сообщества — это РАЗНЫЕ файлы.
    # Имена файлов можно поменять в настройках главной страницы.
    brand_logo_file = settings.get("brand_logo_file") or ""
    brand_avatar_file = settings.get("brand_avatar_file") or ""
    brand_logo = (
        "images/brand/" + brand_logo_file if config._brand_file_exists(brand_logo_file)
        else logo or config.LOGO_URL or ""
    )
    brand_avatar = (
        "images/brand/" + brand_avatar_file if config._brand_file_exists(brand_avatar_file)
        else config.AVATAR_URL or ""
    )

    return {
        "brand_name": settings.get("site_name") or config.BRAND_NAME,
        "brand_tagline": settings.get("site_tagline") or config.BRAND_TAGLINE,
        "slogan": settings.get("slogan") or config.SLOGAN,
        "site_url": config.SITE_URL,
        "site_description": config.SITE_DESCRIPTION,
        "logo_url": logo,
        "brand_logo_url": brand_logo,
        "brand_avatar_url": brand_avatar,
        "brand_avatar_caption": settings.get("brand_avatar_caption", ""),
        "vk_url": settings.get("vk_url", ""),
        "contact_email": settings.get("contact_email", ""),
        "contact_phone": settings.get("contact_phone", ""),
        "contact_text": settings.get("contact_text", ""),
        "settings": settings,
        "content": _site_content(settings),
        "current_year": datetime.now().year,
        # Галерея готовых работ и отзывы для публичных блоков
        "home_gallery": _home_gallery(settings),
        "home_reviews": _home_reviews(settings),
        "reviews_stats": database.review_rating_stats(),
        # CSRF-токен для форм публичного сайта (вход, регистрация, отзывы).
        "csrf_token": _public_csrf_token(),
        # Каталог в виде JSON — корзина в браузере берёт отсюда цены и названия.
        # id схем сохраняются из прежней версии сайта, поэтому старые
        # корзины покупателей продолжают работать.
        "catalog": [pattern_public_data(p) for p in get_active_patterns()],
    }


def _home_gallery(settings):
    """
    Готовые работы для галереи на главной.

    Берём только одобренные работы, у которых есть согласие на публикацию
    и хотя бы одна фотография. Никаких выдуманных картинок.
    """
    try:
        count = int(settings.get("gallery_home_count") or 6)
    except (TypeError, ValueError):
        count = 6
    projects = database.list_public_projects(limit=max(count, 0))
    gallery = []
    for project in projects:
        images = [img for img in project["images"] if _safe_image_path(img)]
        if not images:
            # Без настоящей фотографии работу не показываем
            continue
        gallery.append({
            "id": project["id"],
            "display_name": project["display_name"],
            "story": project["story"],
            "pattern_title": project["pattern_title"],
            "pattern_slug": project["pattern_slug"],
            "images": images,
            "cover": images[0],
        })
    return gallery[:count]


def _home_reviews(settings):
    """Отзывы для блока на главной (только опубликованные)."""
    try:
        count = int(settings.get("reviews_home_count") or 3)
    except (TypeError, ValueError):
        count = 3
    return database.list_reviews(status="approved", limit=max(count, 0))


def format_price(value):
    """
    Красиво показывает цену: 350.0 → «350», 349.5 → «349.50».

    В базе цена хранится числом (может быть дробной), но покупателю
    не нужны лишние нули: «350 ₽» читается лучше, чем «350.0 ₽».
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if number == int(number):
        return str(int(number))
    return f"{number:.2f}"


# Делаем функцию доступной в шаблонах как фильтр: {{ p.price | price }}
app.jinja_env.filters["price"] = format_price


def _public_csrf_token():
    """Токен CSRF для форм публичной части сайта (вход, отзывы и т. п.)."""
    from flask import session
    import security
    if "csrf_token" not in session:
        session["csrf_token"] = security.make_csrf_token()
    return session["csrf_token"]


@app.template_filter("share_text")
def share_text(pattern):
    """Короткий текст приглашения для кнопки «Поделиться»."""
    return f"Посмотрите схему вышивки «{pattern.get('title', '')}» в «Ехидных крестиках»"


@app.template_filter("date_ru")
def date_ru(value):
    """Превращает 2026-10-21 14:35:00 в 21.10.2026."""
    if not value:
        return ""
    try:
        moment = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
        return moment.strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


def _site_content(settings):
    """
    Собирает тексты сайта из настроек.
    Структура такая же, как была в site_content.json — шаблоны не менялись.
    """
    return {
        "hero": {
            "title": settings.get("hero_title", ""),
            "subtitle": settings.get("hero_subtitle", ""),
            "button_text": settings.get("hero_button", "Смотреть схемы"),
        },
        "catalog_title": settings.get("catalog_title", ""),
        "about": {
            "title": settings.get("about_title", "О проекте"),
            "text": settings.get("about_text", ""),
        },
        "preview_block": {
            "title": settings.get("preview_title", ""),
            "subtitle": settings.get("preview_subtitle", ""),
            "empty_message": settings.get("preview_empty_message", ""),
        },
        # Тексты корзины. Пока не вынесены в админ-панель (там их менять
        # не нужно), но структура сохранена такой же, как была в JSON.
        "cart": {
            "title": "Ваша корзина",
            "empty_message": "Пока здесь ни одного вышивального приключения",
            "empty_button": "Выбрать схему",
            "more_button": "Выбрать ещё",
            "checkout_button": "Оформить заказ",
            "total_label": "Итого",
            "count_label": "Схем в корзине",
        },
        "checkout_notice": settings.get(
            "checkout_notice", "Онлайн-оформление заказов появится позже"
        ),
    }


# --------------------------------------------------------------------------
# Маршруты — адреса публичного сайта
# --------------------------------------------------------------------------

@app.route("/")
def index():
    """Главная страница: приветствие + каталог схем + блок «О проекте»."""
    patterns = [pattern_to_view(p) for p in get_active_patterns()]
    return render_template(
        "index.html",
        patterns=patterns,
        categories=visible_categories(),
    )


@app.route("/pattern/<slug>")
def pattern_page(slug):
    """
    Страница одной схемы.

    Черновики (неопубликованные схемы) показываются только администратору —
    остальные посетители получают честную 404.
    """
    pattern = get_pattern(slug)
    if pattern is None:
        abort(404)

    if not pattern["is_published"]:
        # Проверяем, не администратор ли это (импорт здесь, чтобы
        # публичный сайт не зависел от админки без необходимости)
        from admin import current_admin
        if current_admin() is None:
            abort(404)

    view = pattern_to_view(pattern)
    related = [pattern_to_view(p) for p in get_related(slug, count=3)]
    # Отзывы об этой схеме — только опубликованные. Средняя оценка
    # считается тоже только по опубликованным отзывам.
    view["reviews"] = database.list_reviews(status="approved", pattern_id=pattern["id"])
    view["rating_stats"] = database.review_rating_stats(pattern["id"])
    return render_template("pattern.html", p=view, related=related)


@app.route("/cart")
def cart_page():
    """Страница корзины. Товары подгружаются из localStorage на клиенте."""
    return render_template("cart.html")


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    """
    Оформление заказа пока не подключено.

    Вместо демонстрационной формы показываем понятное сообщение:
    «Онлайн-оформление заказов появится позже».
    Никаких платёжных операций не выполняется.
    """
    return render_template("checkout.html")


@app.route("/api/patterns")
def api_patterns():
    """JSON со списком опубликованных схем каталога."""
    return jsonify([pattern_public_data(p) for p in get_active_patterns()])


@app.route("/favicon.ico")
def favicon():
    """Иконка вкладки браузера."""
    return send_from_directory(
        os.path.join(config.STATIC_DIR, "icons"), "favicon.svg",
        mimetype="image/svg+xml",
    )


@app.route("/404")
def page_404_demo():
    """Демонстрационный адрес страницы 404."""
    return render_template("404.html"), 404


@app.errorhandler(404)
def not_found(error):
    """Страница «Не найдено» для любых неизвестных адресов."""
    return render_template("404.html"), 404


@app.errorhandler(403)
def forbidden(error):
    """Доступ запрещён — например, не прошла проверка CSRF-токена."""
    return render_template("403.html", reason=getattr(error, "description", "")), 403


@app.errorhandler(413)
def too_large(error):
    """Загруженный файл больше допустимого размера."""
    return render_template(
        "403.html",
        reason=f"Файл больше {config.MAX_UPLOAD_SIZE_MB} МБ. Уменьшите изображение.",
    ), 413


# --------------------------------------------------------------------------
# Запуск сервера только при прямом запуске файла:  python app.py
# --------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Сайт «{config.BRAND_NAME}» запущен!")
    print(f"Откройте в браузере:  http://{config.HOST}:{config.PORT}")
    print(f"Административная панель:  http://{config.HOST}:{config.PORT}/admin")
    if database.count_admins() == 0:
        print()
        print("Администратор ещё не настроен. Выполните один раз:")
        print("    python setup_admin.py")
    print("Для остановки сервера нажмите Ctrl+C в терминале.")
    if config.DEBUG:
        print("Режим разработки включён (DEBUG). В продакшене поставьте DEBUG = False.")
    try:
        app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
    except OSError as err:
        print("\n" + "=" * 70)
        print(f"Не удалось запустить сервер на порту {config.PORT}.")
        print(f"Причина: {err}")
        print("Скорее всего, этот порт уже занят другой программой.")
        print("Откройте config.py и поменяйте PORT, например, на 5001,")
        print("либо запустите сайт командой:  set EK_PORT=5001 && python app.py")
        print("=" * 70 + "\n")
        raise SystemExit(1)
