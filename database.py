# -*- coding: utf-8 -*-
"""
database.py — работа с базой данных SQLite.

Здесь собрано всё, что касается хранения данных: создание таблиц,
чтение и запись схем, категорий, изображений, настроек сайта и
администратора.

Что важно знать про этот файл:

1) Данные лежат в одном файле — data/catalog.db (обычная база SQLite).
   Она создаётся один раз. При обычном запуске сайта база НЕ пересоздаётся.

2) Ничего не удаляется навсегда: у схем и категорий есть «мягкое удаление»
   (поле deleted_at). Такую запись можно вернуть.

3) Все запросы идут через параметры (знаки ?), поэтому SQL-инъекции
   невозможны: данные из браузера никогда не попадают в текст запроса.

4) Функции простые: открыли соединение — сделали одно действие — закрыли.
   Так код легче читать, а новичку проще разобраться.
"""

import os
import shutil
import sqlite3
from datetime import datetime

import config

# --------------------------------------------------------------------------
# Соединение с базой
# --------------------------------------------------------------------------

def get_connection():
    """
    Открывает соединение с базой данных.

    row_factory = sqlite3.Row позволяет обращаться к колонкам по имени:
    row["title"] вместо row[2].
    """
    os.makedirs(config.DATA_DIR, exist_ok=True)
    connection = sqlite3.connect(config.DB_PATH)

    # Внешние ключи в SQLite по умолчанию выключены — включаем.
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def _now():
    """Текущее время в виде текста: 2026-10-21 14:35:00."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# Создание таблиц
# --------------------------------------------------------------------------

SCHEMA = """
-- ===================== КАТЕГОРИИ =====================
CREATE TABLE IF NOT EXISTS categories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    slug          TEXT NOT NULL UNIQUE,
    position      INTEGER NOT NULL DEFAULT 0,   -- порядок в списке
    is_hidden     INTEGER NOT NULL DEFAULT 0,   -- 1 = скрыта от покупателей
    deleted_at    TEXT,                         -- заполнено = удалена (мягко)
    created_at    TEXT NOT NULL
);

-- ===================== СХЕМЫ ВЫШИВКИ =====================
CREATE TABLE IF NOT EXISTS patterns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,  -- id сохраняем из JSON
    slug            TEXT NOT NULL UNIQUE,               -- адрес страницы
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',           -- краткое описание
    full_description TEXT NOT NULL DEFAULT '',          -- подробное описание
    price           REAL NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'RUB',
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    width           INTEGER,        -- ширина в крестиках
    height          INTEGER,        -- высота в крестиках
    colors          INTEGER,        -- количество цветов
    fabric          TEXT NOT NULL DEFAULT '',
    fabric_count    INTEGER,        -- каунт канвы
    finished_size   TEXT NOT NULL DEFAULT '',  -- размер работы (как ввёл автор)
    difficulty      TEXT NOT NULL DEFAULT '',
    main_image      TEXT NOT NULL DEFAULT '',  -- главное изображение
    preview_10x10   TEXT NOT NULL DEFAULT '',  -- фрагмент схемы 10×10
    is_published    INTEGER NOT NULL DEFAULT 0,  -- 1 = опубликовано
    deleted_at      TEXT,                        -- заполнено = в корзине (мягко)
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Дополнительные фотографии схемы (галерея)
CREATE TABLE IF NOT EXISTS pattern_images (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id  INTEGER NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
    path        TEXT NOT NULL,      -- путь относительно папки static/
    caption     TEXT NOT NULL DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0,  -- порядок в галерее
    created_at  TEXT NOT NULL
);

-- ===================== НАСТРОЙКИ САЙТА =====================
-- Простая таблица «ключ — значение»: удобно расширять новыми настройками
CREATE TABLE IF NOT EXISTS site_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT ''
);

-- ===================== АДМИНИСТРАТОР =====================
CREATE TABLE IF NOT EXISTS admin_users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,   -- только хеш! Сам пароль нигде не хранится
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- Попытки входа: нужны, чтобы ограничить перебор пароля
CREATE TABLE IF NOT EXISTS login_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL DEFAULT '',
    ip          TEXT NOT NULL DEFAULT '',
    success     INTEGER NOT NULL DEFAULT 0,
    attempted_at TEXT NOT NULL
);

-- Индексы ускоряют поиск по частым полям
CREATE INDEX IF NOT EXISTS idx_patterns_slug ON patterns(slug);
CREATE INDEX IF NOT EXISTS idx_patterns_category ON patterns(category_id);
CREATE INDEX IF NOT EXISTS idx_images_pattern ON pattern_images(pattern_id);

-- ==========================================================================
-- НОВЫЕ ТАБЛИЦЫ: ЛИЧНЫЕ КАБИНЕТЫ, БИБЛИОТЕКА, ОТШИВЫ, ОТЗЫВЫ
-- ==========================================================================
-- Все таблицы создаются через CREATE TABLE IF NOT EXISTS, поэтому
-- обновление базы безопасно: существующие данные не пересоздаются
-- и не теряются (см. комментарий к init_db).

-- ===================== ПОКУПАТЕЛИ =====================
-- Отдельная таблица. Администратор (admin_users) и покупатель — это
-- разные роли и разные записи, их нельзя перепутать.
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL DEFAULT '',   -- имя, как ввёл покупатель
    nickname          TEXT NOT NULL DEFAULT '',   -- никнейм (необязательный)
    email             TEXT NOT NULL,              -- почта для входа (уникальна)
    password_hash     TEXT NOT NULL,              -- только хеш пароля
    email_confirmed   INTEGER NOT NULL DEFAULT 0, -- 1 = почта подтверждена
    is_blocked        INTEGER NOT NULL DEFAULT 0, -- 1 = аккаунт заблокирован
    -- Как показывать имя публично: full / nickname / first
    display_name_mode TEXT NOT NULL DEFAULT 'first',
    -- Свой вариант отображаемого имени (если покупатель ввёл его сам)
    display_name_custom TEXT NOT NULL DEFAULT '',
    deleted_at        TEXT,                       -- мягкое удаление
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    last_login_at     TEXT
);

-- Токены подтверждения почты и сброса пароля.
-- Хранится только ХЕШ токена: по базе восстановить ссылку нельзя.
CREATE TABLE IF NOT EXISTS user_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL,
    purpose     TEXT NOT NULL,          -- confirm_email / reset_password
    expires_at  TEXT NOT NULL,
    used_at     TEXT,                   -- заполнено = токен уже использован
    created_at  TEXT NOT NULL
);

-- Попытки входа покупателей (ограничение перебора пароля).
-- Отдельная таблица, чтобы не смешивать с попытками входа администратора.
CREATE TABLE IF NOT EXISTS user_login_attempts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    email        TEXT NOT NULL DEFAULT '',
    ip           TEXT NOT NULL DEFAULT '',
    success      INTEGER NOT NULL DEFAULT 0,
    attempted_at TEXT NOT NULL
);

-- ===================== ЦИФРОВЫЕ ФАЙЛЫ СХЕМ =====================
-- PDF / Saga / Paradise — файлы, которые покупатель скачивает после
-- покупки. В базе хранится только ВНУТРЕННЕЕ имя файла (без пути):
-- настоящий файл лежит в папке protected/, вне public static.
CREATE TABLE IF NOT EXISTS pattern_files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id   INTEGER NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
    format       TEXT NOT NULL,             -- pdf / saga / paradise / other
    title        TEXT NOT NULL DEFAULT '',  -- как показать покупателю
    stored_name  TEXT NOT NULL,             -- имя файла в папке protected/
    original_name TEXT NOT NULL DEFAULT '',
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    is_active    INTEGER NOT NULL DEFAULT 1, -- 1 = доступен для скачивания
    created_at   TEXT NOT NULL
);

-- ===================== ЗАКАЗЫ =====================
-- Структура для будущего подключения продаж. Оплата пока не подключена,
-- поэтому сайт НЕ создаёт заказы автоматически.
CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    order_number  TEXT NOT NULL UNIQUE,   -- человекочитаемый номер
    status        TEXT NOT NULL DEFAULT 'manual',
                  -- manual (ручной) / paid / cancelled — задел на будущее
    total         REAL NOT NULL DEFAULT 0,
    currency      TEXT NOT NULL DEFAULT 'RUB',
    note          TEXT NOT NULL DEFAULT '',  -- комментарий администратора
    source        TEXT NOT NULL DEFAULT 'manual',
                  -- manual (внесён вручную) / site (когда появятся продажи)
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    pattern_id  INTEGER REFERENCES patterns(id) ON DELETE SET NULL,
    title       TEXT NOT NULL DEFAULT '',  -- название на момент заказа
    price       REAL NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

-- ===================== ПРАВА ДОСТУПА (БИБЛИОТЕКА) =====================
-- Право скачивания конкретной схемы. Пока онлайн-продажи не подключены,
-- права выдаёт ТОЛЬКО администратор. Добавление в корзину НЕ создаёт
-- право доступа.
CREATE TABLE IF NOT EXISTS user_entitlements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pattern_id   INTEGER NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
    order_id     INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    granted_at   TEXT NOT NULL,
    revoked_at   TEXT,                     -- заполнено = право отозвано
    granted_by   TEXT NOT NULL DEFAULT 'admin',
    note         TEXT NOT NULL DEFAULT '',
    -- Откуда взялось право:
    --   'site'   — покупка на нашем сайте (её можно отметить как подтверждённую);
    --   'manual' — администратор внёс вручную (покупка на другой площадке).
    -- Отметка «Покупка подтверждена» в отзывах ставится только для 'site'.
    source       TEXT NOT NULL DEFAULT 'manual',
    UNIQUE (user_id, pattern_id)           -- одно право на пару
);

-- ===================== ГОТОВЫЕ РАБОТЫ (ОТШИВЫ) =====================
CREATE TABLE IF NOT EXISTS finished_projects (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
    pattern_id        INTEGER REFERENCES patterns(id) ON DELETE SET NULL,
    story             TEXT NOT NULL DEFAULT '',   -- рассказ о процессе
    display_name      TEXT NOT NULL DEFAULT '',   -- имя рукодельницы
    status            TEXT NOT NULL DEFAULT 'pending',
                      -- pending / approved / rejected / hidden / withdrawn
    moderation_note   TEXT NOT NULL DEFAULT '',   -- причина отклонения
    owns_photos       INTEGER NOT NULL DEFAULT 0, -- подтверждение авторства
    publish_consent   INTEGER NOT NULL DEFAULT 0, -- согласие на публикацию
    show_on_home      INTEGER NOT NULL DEFAULT 1, -- показывать на главной
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    approved_at       TEXT
);

CREATE TABLE IF NOT EXISTS finished_project_images (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES finished_projects(id) ON DELETE CASCADE,
    stored_path TEXT NOT NULL,        -- оптимизированная копия (в static/)
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

-- ===================== ОТЗЫВЫ =====================
CREATE TABLE IF NOT EXISTS reviews (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
    pattern_id        INTEGER REFERENCES patterns(id) ON DELETE SET NULL,
    category          TEXT NOT NULL DEFAULT 'pattern',
                      -- pattern / design / shop
    rating            INTEGER NOT NULL DEFAULT 0,  -- от 1 до 5
    text              TEXT NOT NULL DEFAULT '',
    photo_path        TEXT NOT NULL DEFAULT '',    -- необязательное фото
    display_name      TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'pending',
                      -- pending / approved / rejected / hidden
    moderation_note   TEXT NOT NULL DEFAULT '',
    -- Подтверждённая покупка: 1 только если схема реально куплена на сайте
    verified_purchase INTEGER NOT NULL DEFAULT 0,
    content_hash      TEXT NOT NULL DEFAULT '',    -- защита от копий
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    approved_at       TEXT
);

-- ===================== ЖУРНАЛ МОДЕРАЦИИ =====================
-- Кто и что сделал с отшивом или отзывом. Нужно для честной истории.
CREATE TABLE IF NOT EXISTS moderation_actions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type  TEXT NOT NULL,      -- project / review
    target_id    INTEGER NOT NULL,
    action       TEXT NOT NULL,      -- approve / reject / hide / delete / withdraw
    reason       TEXT NOT NULL DEFAULT '',
    admin_name   TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);

-- Индексы новых таблиц
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_tokens_user ON user_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_patfiles_pattern ON pattern_files(pattern_id);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_entitlements_user ON user_entitlements(user_id);
CREATE INDEX IF NOT EXISTS idx_entitlements_pattern ON user_entitlements(pattern_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON finished_projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_user ON finished_projects(user_id);
CREATE INDEX IF NOT EXISTS idx_proj_images_project ON finished_project_images(project_id);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);
CREATE INDEX IF NOT EXISTS idx_reviews_pattern ON reviews(pattern_id);
CREATE INDEX IF NOT EXISTS idx_reviews_user ON reviews(user_id);
CREATE INDEX IF NOT EXISTS idx_moderation_target ON moderation_actions(target_type, target_id);
"""


def init_db():
    """
    Создаёт таблицы, если их ещё нет. Существующие данные не трогает.

    Эту функцию безопасно вызывать при каждом запуске: она ничего
    не удаляет и не пересоздаёт.
    """
    connection = get_connection()
    try:
        connection.executescript(SCHEMA)
        _add_missing_columns(connection)
        _seed_settings(connection)
        connection.commit()
    finally:
        connection.close()


# Какие столбцы могли появиться уже после первого запуска сайта.
# CREATE TABLE IF NOT EXISTS не добавляет новые столбцы в существующую
# таблицу, поэтому дописываем их аккуратно и без потери данных.
_ADDED_COLUMNS = {
    "user_entitlements": [
        # Источник права: 'site' (покупка на сайте) или 'manual' (вручную).
        ("source", "TEXT NOT NULL DEFAULT 'manual'"),
    ],
    "reviews": [
        ("content_hash", "TEXT NOT NULL DEFAULT ''"),
    ],
    "finished_projects": [
        ("moderation_note", "TEXT NOT NULL DEFAULT ''"),
    ],
}


def _add_missing_columns(connection):
    """
    Добавляет недостающие столбцы в уже существующие таблицы.

    Это «мягкая» миграция: данные не удаляются и не пересоздаются.
    Если столбец уже есть — ничего не делаем.
    """
    for table, columns in _ADDED_COLUMNS.items():
        existing = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if not existing:
            continue  # таблицы ещё нет — её создаст SCHEMA
        for name, definition in columns:
            if name not in existing:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                )


def _seed_settings(connection):
    """Заполняет настройки сайта значениями по умолчанию (только пустые ключи)."""
    defaults = {
        "site_name": config.BRAND_NAME,
        "site_tagline": config.BRAND_TAGLINE,
        "slogan": config.SLOGAN,
        "hero_title": "",
        "hero_subtitle": "",
        "hero_button": "Смотреть схемы",
        "about_title": "О проекте",
        "about_text": "",
        "logo": "",
        "vk_url": "",
        "contact_email": "",
        "contact_phone": "",
        "contact_text": "",
        "catalog_title": "",
        "preview_title": "Рассмотреть схему поближе",
        "preview_subtitle": (
            "Фрагмент электронной схемы — 10×10 клеточек, чтобы оценить "
            "детализацию и обозначения"
        ),
        "preview_empty_message": "Фрагмент схемы скоро появится",
        "checkout_notice": "Онлайн-оформление заказов появится позже",

        # --- Галерея готовых работ на главной («Хвастики без скромности») ---
        "gallery_title": "Хвастики без скромности",
        "gallery_subtitle": "Ваши готовые работы по схемам «Ехидных крестиков»",
        "gallery_home_count": "6",        # сколько работ показывать на главной
        "gallery_empty_message": (
            "Здесь скоро появятся готовые работы. Поделиться своим отшивом "
            "можно из личного кабинета — мы покажем его после проверки."
        ),

        # --- Блок отзывов на главной («Ваши впечатления») ---
        "reviews_title": "Ваши впечатления",
        "reviews_subtitle": (
            "Отзывы о схемах, вышивальном процессе и работе магазина"
        ),
        "reviews_home_count": "3",        # сколько отзывов показывать на главной
        "reviews_empty_message": (
            "Отзывов пока нет. Оставить отзыв может зарегистрированный "
            "покупатель с подтверждённой почтой."
        ),

        # --- Фирменные изображения (логотип и аватар сообщества) ---
        # Пусто = берём файлы с именами по умолчанию (logo.jpg /
        # community-avatar.png). Администратор может указать другие имена.
        "brand_logo_file": "",
        "brand_avatar_file": "",
        # Подпись к аватару пуста по умолчанию: на первом экране показываем
        # только изображение, без текста.
        "brand_avatar_caption": "",
    }
    for key, value in defaults.items():
        connection.execute(
            "INSERT OR IGNORE INTO site_settings (key, value) VALUES (?, ?)",
            (key, value),
        )


# --------------------------------------------------------------------------
# НАСТРОЙКИ САЙТА
# --------------------------------------------------------------------------

def get_settings():
    """Возвращает все настройки сайта словарём {ключ: значение}."""
    connection = get_connection()
    try:
        rows = connection.execute("SELECT key, value FROM site_settings").fetchall()
        return {row["key"]: row["value"] for row in rows}
    finally:
        connection.close()


def get_setting(key, default=""):
    """Возвращает одну настройку по имени."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT value FROM site_settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default
    finally:
        connection.close()


def set_setting(key, value):
    """Сохраняет одну настройку (создаёт или перезаписывает)."""
    connection = get_connection()
    try:
        connection.execute(
            "INSERT INTO site_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, "" if value is None else str(value)),
        )
        connection.commit()
    finally:
        connection.close()


def set_settings(values):
    """Сохраняет сразу несколько настроек: {"site_name": "...", ...}."""
    connection = get_connection()
    try:
        for key, value in values.items():
            connection.execute(
                "INSERT INTO site_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, "" if value is None else str(value)),
            )
        connection.commit()
    finally:
        connection.close()


# --------------------------------------------------------------------------
# КАТЕГОРИИ
# --------------------------------------------------------------------------

def _category_from_row(row):
    """Превращает строку базы в обычный словарь."""
    return {
        "id": row["id"],
        "name": row["name"],
        "slug": row["slug"],
        "position": row["position"],
        "is_hidden": bool(row["is_hidden"]),
        "deleted_at": row["deleted_at"],
        "created_at": row["created_at"],
    }


def list_categories(include_hidden=True, include_deleted=False):
    """Список категорий по порядку. По умолчанию — все, кроме удалённых."""
    connection = get_connection()
    try:
        query = "SELECT * FROM categories WHERE 1 = 1"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        if not include_hidden:
            query += " AND is_hidden = 0"
        query += " ORDER BY position, name"
        return [_category_from_row(row) for row in connection.execute(query)]
    finally:
        connection.close()


def get_category(category_id):
    """Одна категория по id."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        return _category_from_row(row) if row else None
    finally:
        connection.close()


def get_category_by_name(name):
    """Находит категорию по названию (без учёта регистра)."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM categories WHERE name = ? COLLATE NOCASE AND deleted_at IS NULL",
            (name,),
        ).fetchone()
        return _category_from_row(row) if row else None
    finally:
        connection.close()


def add_category(name, slug="", position=None):
    """Добавляет категорию и возвращает её id."""
    connection = get_connection()
    try:
        if position is None:
            row = connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 AS next FROM categories"
            ).fetchone()
            position = row["next"]

        # Адрес категории должен быть уникальным. Если такой уже есть
        # (например, две разные категории зовутся похоже) — добавляем число.
        base_slug = slug.strip() or slug_from_name(name)
        category_slug = base_slug
        counter = 2
        while connection.execute(
            "SELECT 1 FROM categories WHERE slug = ?", (category_slug,)
        ).fetchone():
            category_slug = f"{base_slug}-{counter}"
            counter += 1

        cursor = connection.execute(
            "INSERT INTO categories (name, slug, position, is_hidden, created_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (name.strip(), category_slug, position, _now()),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def update_category(category_id, name=None, is_hidden=None, position=None):
    """Меняет название, видимость или порядок категории."""
    fields = []
    values = []
    if name is not None:
        fields.append("name = ?")
        values.append(name.strip())
    if is_hidden is not None:
        fields.append("is_hidden = ?")
        values.append(1 if is_hidden else 0)
    if position is not None:
        fields.append("position = ?")
        values.append(int(position))

    if not fields:
        return

    values.append(category_id)
    connection = get_connection()
    try:
        connection.execute(
            f"UPDATE categories SET {', '.join(fields)} WHERE id = ?", values
        )
        connection.commit()
    finally:
        connection.close()


def count_category_patterns(category_id):
    """Сколько схем привязано к категории (учитывая черновики)."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM patterns "
            "WHERE category_id = ? AND deleted_at IS NULL",
            (category_id,),
        ).fetchone()
        return row["total"]
    finally:
        connection.close()


def delete_category(category_id, move_to_category_id=None):
    """
    Удаляет категорию (мягко, то есть её можно вернуть).

    Если к категории привязаны схемы, а новая категория не указана,
    возвращаем количество схем и НЕ удаляем: администратор должен
    сначала решить, что с ними делать.
    """
    linked = count_category_patterns(category_id)
    if linked and move_to_category_id is None:
        return {"deleted": False, "linked": linked}

    connection = get_connection()
    try:
        if linked and move_to_category_id is not None:
            connection.execute(
                "UPDATE patterns SET category_id = ? WHERE category_id = ?",
                (move_to_category_id, category_id),
            )
        connection.execute(
            "UPDATE categories SET deleted_at = ? WHERE id = ?",
            (_now(), category_id),
        )
        connection.commit()
        return {"deleted": True, "linked": linked}
    finally:
        connection.close()


def restore_category(category_id):
    """Возвращает удалённую категорию."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE categories SET deleted_at = NULL WHERE id = ?", (category_id,)
        )
        connection.commit()
    finally:
        connection.close()


def reorder_categories(ordered_ids):
    """Задаёт порядок категорий: ordered_ids = [3, 1, 2]."""
    connection = get_connection()
    try:
        for index, category_id in enumerate(ordered_ids, start=1):
            connection.execute(
                "UPDATE categories SET position = ? WHERE id = ?",
                (index, category_id),
            )
        connection.commit()
    finally:
        connection.close()


# --------------------------------------------------------------------------
# СХЕМЫ
# --------------------------------------------------------------------------

def _pattern_from_row(row):
    """Превращает строку базы в словарь схемы."""
    keys = row.keys()
    return {
        "id": row["id"],
        "slug": row["slug"],
        "title": row["title"],
        "description": row["description"],
        "full_description": row["full_description"],
        "price": row["price"],
        "currency": row["currency"],
        "category_id": row["category_id"],
        "category": row["category_name"] if "category_name" in keys else "",
        "width": row["width"],
        "height": row["height"],
        "colors": row["colors"],
        "fabric": row["fabric"],
        "fabric_count": row["fabric_count"],
        "finished_size": row["finished_size"],
        "difficulty": row["difficulty"],
        "main_image": row["main_image"],
        "preview_10x10": row["preview_10x10"],
        "is_published": bool(row["is_published"]),
        "deleted_at": row["deleted_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


_PATTERN_SELECT = """
SELECT p.*, c.name AS category_name
FROM patterns p
LEFT JOIN categories c ON c.id = p.category_id
"""


def list_patterns(
    search="",
    status="",
    category_id=None,
    sort="updated_desc",
    include_deleted=False,
):
    """
    Список схем для административной панели.

    search   — поиск по названию (часть слова)
    status   — "published" / "draft" / "" (все)
    category_id — id категории или None
    sort     — updated_desc, updated_asc, price_asc, price_desc,
               title_asc, title_desc
    """
    query = _PATTERN_SELECT + " WHERE 1 = 1"
    values = []

    if not include_deleted:
        query += " AND p.deleted_at IS NULL"
    if search:
        query += " AND p.title LIKE ?"
        values.append(f"%{search}%")
    if status == "published":
        query += " AND p.is_published = 1"
    elif status == "draft":
        query += " AND p.is_published = 0"
    if category_id:
        query += " AND p.category_id = ?"
        values.append(category_id)

    order = {
        "updated_desc": "p.updated_at DESC",
        "updated_asc": "p.updated_at ASC",
        "price_asc": "p.price ASC",
        "price_desc": "p.price DESC",
        "title_asc": "p.title ASC",
        "title_desc": "p.title DESC",
    }.get(sort, "p.updated_at DESC")
    query += f" ORDER BY {order}"

    connection = get_connection()
    try:
        rows = connection.execute(query, values).fetchall()
        return [_pattern_from_row(row) for row in rows]
    finally:
        connection.close()


def list_published_patterns(category_id=None, sort="title_asc"):
    """Опубликованные и не удалённые схемы — для публичной части сайта."""
    query = _PATTERN_SELECT + " WHERE p.is_published = 1 AND p.deleted_at IS NULL"
    values = []
    if category_id:
        query += " AND p.category_id = ?"
        values.append(category_id)
    order = {
        "title_asc": "p.title ASC",
        "title_desc": "p.title DESC",
        "price_asc": "p.price ASC",
        "price_desc": "p.price DESC",
        "updated_desc": "p.updated_at DESC",
    }.get(sort, "p.title ASC")
    query += f" ORDER BY {order}"

    connection = get_connection()
    try:
        rows = connection.execute(query, values).fetchall()
        return [_pattern_from_row(row) for row in rows]
    finally:
        connection.close()


def get_pattern_by_slug(slug):
    """Одна схема по адресу страницы (включая черновики и неопубликованные)."""
    connection = get_connection()
    try:
        row = connection.execute(
            _PATTERN_SELECT + " WHERE p.slug = ?", (slug,)
        ).fetchone()
        return _pattern_from_row(row) if row else None
    finally:
        connection.close()


def get_pattern(pattern_id):
    """Одна схема по id."""
    connection = get_connection()
    try:
        row = connection.execute(
            _PATTERN_SELECT + " WHERE p.id = ?", (pattern_id,)
        ).fetchone()
        return _pattern_from_row(row) if row else None
    finally:
        connection.close()


def get_pattern_by_title(title):
    """Находит схему по точному названию — нужно при импорте, чтобы не дублировать."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM patterns WHERE title = ?", (title,)
        ).fetchone()
        return _pattern_from_row(row) if row else None
    finally:
        connection.close()


def slug_exists(slug, exclude_id=None):
    """Проверяет, занят ли адрес страницы (slug)."""
    connection = get_connection()
    try:
        if exclude_id:
            row = connection.execute(
                "SELECT id FROM patterns WHERE slug = ? AND id != ?",
                (slug, exclude_id),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT id FROM patterns WHERE slug = ?", (slug,)
            ).fetchone()
        return row is not None
    finally:
        connection.close()


def create_pattern(data, images=None, publish=False):
    """
    Создаёт новую схему.

    data   — словарь с полями (title, price, ...)
    images — список путей к дополнительным фотографиям
    publish — True = сразу опубликовать, False = сохранить черновик

    Возвращает id новой схемы.
    """
    moment = _now()
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO patterns (
                slug, title, description, full_description, price, currency,
                category_id, width, height, colors, fabric, fabric_count,
                finished_size, difficulty, main_image, preview_10x10,
                is_published, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["slug"], data["title"], data.get("description", ""),
                data.get("full_description", ""), data.get("price", 0),
                data.get("currency", "RUB"), data.get("category_id"),
                data.get("width"), data.get("height"), data.get("colors"),
                data.get("fabric", ""), data.get("fabric_count"),
                data.get("finished_size", ""), data.get("difficulty", ""),
                data.get("main_image", ""), data.get("preview_10x10", ""),
                1 if publish else 0, moment, moment,
            ),
        )
        pattern_id = cursor.lastrowid
        _replace_images(connection, pattern_id, images or [])
        connection.commit()
        return pattern_id
    finally:
        connection.close()


def update_pattern(pattern_id, data, images=None, publish=None):
    """
    Обновляет схему. Незаполненные поля (None) остаются прежними —
    поэтому редактирование не теряет данные.
    """
    fields = []
    values = []
    allowed = (
        "slug", "title", "description", "full_description", "price", "currency",
        "category_id", "width", "height", "colors", "fabric", "fabric_count",
        "finished_size", "difficulty", "main_image", "preview_10x10",
    )
    for field in allowed:
        if field in data and data[field] is not None:
            fields.append(f"{field} = ?")
            values.append(data[field])

    if publish is not None:
        fields.append("is_published = ?")
        values.append(1 if publish else 0)

    fields.append("updated_at = ?")
    values.append(_now())
    values.append(pattern_id)

    connection = get_connection()
    try:
        connection.execute(
            f"UPDATE patterns SET {', '.join(fields)} WHERE id = ?", values
        )
        if images is not None:
            _replace_images(connection, pattern_id, images)
        connection.commit()
    finally:
        connection.close()


def _replace_images(connection, pattern_id, images):
    """Переписывает галерею схемы: старый список заменяем новым по порядку."""
    connection.execute(
        "DELETE FROM pattern_images WHERE pattern_id = ?", (pattern_id,)
    )
    moment = _now()
    for position, path in enumerate(images, start=1):
        if not path:
            continue
        connection.execute(
            "INSERT INTO pattern_images (pattern_id, path, position, created_at) "
            "VALUES (?, ?, ?, ?)",
            (pattern_id, path, position, moment),
        )


def get_pattern_images(pattern_id):
    """Дополнительные фотографии схемы по порядку."""
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT path FROM pattern_images WHERE pattern_id = ? "
            "ORDER BY position, id",
            (pattern_id,),
        ).fetchall()
        return [row["path"] for row in rows]
    finally:
        connection.close()


def set_published(pattern_id, published):
    """Публикует схему или снимает её с публикации."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE patterns SET is_published = ?, updated_at = ? WHERE id = ?",
            (1 if published else 0, _now(), pattern_id),
        )
        connection.commit()
    finally:
        connection.close()


def duplicate_pattern(pattern_id):
    """Создаёт копию схемы (черновик) и возвращает id копии."""
    original = get_pattern(pattern_id)
    if original is None:
        return None
    images = get_pattern_images(pattern_id)

    # Новое название и адрес: добавляем слово «копия» и число
    new_title = original["title"] + " (копия)"
    base_slug = (original["slug"] + "-kopiya")[:180]
    new_slug = base_slug
    counter = 2
    while slug_exists(new_slug):
        new_slug = f"{base_slug}-{counter}"
        counter += 1

    data = dict(original)
    data["title"] = new_title
    data["slug"] = new_slug
    return create_pattern(data, images=images, publish=False)


def soft_delete_pattern(pattern_id):
    """Мягкое удаление: схема перестаёт показываться, но её можно вернуть."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE patterns SET deleted_at = ?, updated_at = ? WHERE id = ?",
            (_now(), _now(), pattern_id),
        )
        connection.commit()
    finally:
        connection.close()


def restore_pattern(pattern_id):
    """Возвращает схему из мягко удалённых."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE patterns SET deleted_at = NULL, updated_at = ? WHERE id = ?",
            (_now(), pattern_id),
        )
        connection.commit()
    finally:
        connection.close()


def count_patterns(include_deleted=False):
    """Общее количество схем. Нужно для проверки «не удалить всё сразу»."""
    connection = get_connection()
    try:
        query = "SELECT COUNT(*) AS total FROM patterns"
        if not include_deleted:
            query += " WHERE deleted_at IS NULL"
        return connection.execute(query).fetchone()["total"]
    finally:
        connection.close()


def count_by_status():
    """Сколько схем опубликовано, а сколько черновиков."""
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT is_published, COUNT(*) AS total FROM patterns "
            "WHERE deleted_at IS NULL GROUP BY is_published"
        ).fetchall()
        result = {"published": 0, "draft": 0}
        for row in rows:
            if row["is_published"]:
                result["published"] = row["total"]
            else:
                result["draft"] = row["total"]
        return result
    finally:
        connection.close()


def category_counts():
    """Словарь {id категории: количество схем} для списка категорий."""
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT category_id, COUNT(*) AS total FROM patterns "
            "WHERE deleted_at IS NULL AND category_id IS NOT NULL "
            "GROUP BY category_id"
        ).fetchall()
        return {row["category_id"]: row["total"] for row in rows}
    finally:
        connection.close()


# --------------------------------------------------------------------------
# АДМИНИСТРАТОР
# --------------------------------------------------------------------------

def get_admin(username=None):
    """Возвращает администратора по логину (или первого, если логин не указан)."""
    connection = get_connection()
    try:
        if username is None:
            row = connection.execute(
                "SELECT * FROM admin_users ORDER BY id LIMIT 1"
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM admin_users WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "password_hash": row["password_hash"],
            "created_at": row["created_at"],
        }
    finally:
        connection.close()


def count_admins():
    """Сколько администраторов заведено (0 = панель ещё не настроена)."""
    connection = get_connection()
    try:
        return connection.execute(
            "SELECT COUNT(*) AS total FROM admin_users"
        ).fetchone()["total"]
    finally:
        connection.close()


def set_admin(username, password_hash):
    """
    Создаёт администратора или меняет логин и пароль существующего.
    Пароль передаётся уже в виде хеша.
    """
    moment = _now()
    connection = get_connection()
    try:
        existing = connection.execute(
            "SELECT id FROM admin_users LIMIT 1"
        ).fetchone()
        if existing:
            connection.execute(
                "UPDATE admin_users SET username = ?, password_hash = ?, updated_at = ? "
                "WHERE id = ?",
                (username, password_hash, moment, existing["id"]),
            )
        else:
            connection.execute(
                "INSERT INTO admin_users (username, password_hash, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (username, password_hash, moment, moment),
            )
        connection.commit()
    finally:
        connection.close()


# --------------------------------------------------------------------------
# ОГРАНИЧЕНИЕ ПОПЫТОК ВХОДА
# --------------------------------------------------------------------------

def add_login_attempt(username, ip, success):
    """Записывает попытку входа — удачную или нет."""
    connection = get_connection()
    try:
        connection.execute(
            "INSERT INTO login_attempts (username, ip, success, attempted_at) "
            "VALUES (?, ?, ?, ?)",
            (username or "", ip or "", 1 if success else 0, _now()),
        )
        connection.commit()
    finally:
        connection.close()


def recent_failed_attempts(ip, minutes=15):
    """Сколько раз за последние minutes минут пароль был введён неверно."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM login_attempts "
            "WHERE ip = ? AND success = 0 "
            "AND attempted_at > datetime('now', 'localtime', ?)",
            (ip or "", f"-{int(minutes)} minutes"),
        ).fetchone()
        return row["total"]
    finally:
        connection.close()


def clear_login_attempts(ip):
    """После успешного входа убираем неудачные попытки с этого адреса."""
    connection = get_connection()
    try:
        connection.execute(
            "DELETE FROM login_attempts WHERE ip = ? AND success = 0", (ip or "",)
        )
        connection.commit()
    finally:
        connection.close()


# --------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНОЕ: адрес страницы (slug) из названия
# --------------------------------------------------------------------------

# Таблица замены русских букв на латиницу
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slug_from_name(name):
    """
    Делает из названия адрес страницы: «Ехидная лисица» → «ehidnaya-lisitsa».
    Если получилось пусто — вернёт «shema».
    """
    result = []
    for char in (name or "").lower():
        if char in _TRANSLIT:
            result.append(_TRANSLIT[char])
        elif char.isalnum() and char.isascii():
            result.append(char)
        else:
            result.append("-")
    slug = "".join(result)
    # Убираем повторяющиеся дефисы и обрезаем по краям
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug[:180] or "shema"


def unique_slug(name, exclude_id=None):
    """Делает адрес страницы уникальным: при совпадении добавляет -2, -3..."""
    base = slug_from_name(name)
    slug = base
    counter = 2
    while slug_exists(slug, exclude_id=exclude_id):
        slug = f"{base}-{counter}"
        counter += 1
    return slug


# --------------------------------------------------------------------------
# ПОКУПАТЕЛИ (ЛИЧНЫЕ КАБИНЕТЫ)
# --------------------------------------------------------------------------

def _user_from_row(row):
    """Превращает строку таблицы users в словарь. Хеш пароля НЕ отдаём наружу."""
    return {
        "id": row["id"],
        "name": row["name"],
        "nickname": row["nickname"],
        "email": row["email"],
        "email_confirmed": bool(row["email_confirmed"]),
        "is_blocked": bool(row["is_blocked"]),
        "display_name_mode": row["display_name_mode"],
        "display_name_custom": row["display_name_custom"],
        "deleted_at": row["deleted_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row["last_login_at"],
    }


def _email_exists(connection, email, exclude_id=None):
    """Занят ли адрес почты другим покупателем (без учёта регистра)."""
    if exclude_id:
        row = connection.execute(
            "SELECT id FROM users WHERE email = ? COLLATE NOCASE AND id != ?",
            (email, exclude_id),
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email,)
        ).fetchone()
    return row is not None


def create_user(name, email, password_hash, nickname="", email_confirmed=False):
    """
    Создаёт покупателя. Возвращает id новой учётной записи.
    Пароль передаётся уже в виде хеша. Почта должна быть уникальной.
    """
    moment = _now()
    connection = get_connection()
    try:
        if _email_exists(connection, email):
            return None
        cursor = connection.execute(
            """
            INSERT INTO users (
                name, nickname, email, password_hash, email_confirmed,
                display_name_mode, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'first', ?, ?)
            """,
            (
                (name or "").strip(), (nickname or "").strip(), email.strip(),
                password_hash, 1 if email_confirmed else 0, moment, moment,
            ),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def get_user(user_id):
    """Покупатель по id (без хеша пароля)."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return _user_from_row(row) if row else None
    finally:
        connection.close()


def get_user_by_email(email):
    """Покупатель по адресу почты (без учёта регистра)."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE AND deleted_at IS NULL",
            ((email or "").strip(),),
        ).fetchone()
        return _user_from_row(row) if row else None
    finally:
        connection.close()


def get_user_password_hash(user_id):
    """Отдельно возвращает хеш пароля — нужен только для проверки входа."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return row["password_hash"] if row else None
    finally:
        connection.close()


def get_user_by_email_with_hash(email):
    """Возвращает покупателя вместе с хешем пароля — для страницы входа."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE AND deleted_at IS NULL",
            ((email or "").strip(),),
        ).fetchone()
        if row is None:
            return None
        user = _user_from_row(row)
        user["password_hash"] = row["password_hash"]
        return user
    finally:
        connection.close()


def update_user(user_id, data):
    """Меняет поля профиля. Разрешены только перечисленные."""
    allowed = ("name", "nickname", "display_name_mode", "display_name_custom")
    fields = []
    values = []
    for field in allowed:
        if field in data and data[field] is not None:
            fields.append(f"{field} = ?")
            values.append(data[field])
    if not fields:
        return
    fields.append("updated_at = ?")
    values.append(_now())
    values.append(user_id)
    connection = get_connection()
    try:
        connection.execute(
            f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values
        )
        connection.commit()
    finally:
        connection.close()


def set_user_password(user_id, password_hash):
    """Меняет пароль покупателя (хеш)."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (password_hash, _now(), user_id),
        )
        connection.commit()
    finally:
        connection.close()


def set_user_email(user_id, email):
    """Меняет адрес почты (например, при восстановлении доступа)."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE users SET email = ?, updated_at = ? WHERE id = ?",
            (email.strip(), _now(), user_id),
        )
        connection.commit()
    finally:
        connection.close()


def confirm_user_email(user_id):
    """Отмечает почту покупателя как подтверждённую."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE users SET email_confirmed = 1, updated_at = ? WHERE id = ?",
            (_now(), user_id),
        )
        connection.commit()
    finally:
        connection.close()


def set_user_blocked(user_id, blocked):
    """Блокирует или разблокирует аккаунт покупателя."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE users SET is_blocked = ?, updated_at = ? WHERE id = ?",
            (1 if blocked else 0, _now(), user_id),
        )
        connection.commit()
    finally:
        connection.close()


def touch_user_login(user_id):
    """Запоминает время последнего входа."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (_now(), _now(), user_id),
        )
        connection.commit()
    finally:
        connection.close()


def list_users(search="", include_deleted=False):
    """
    Список покупателей для админ-панели (сначала новые).
    Поиск — по имени, никнейму или почте.
    """
    query = "SELECT * FROM users WHERE 1 = 1"
    values = []
    if not include_deleted:
        query += " AND deleted_at IS NULL"
    if search:
        query += " AND (name LIKE ? OR nickname LIKE ? OR email LIKE ?)"
        like = f"%{search}%"
        values.extend([like, like, like])
    query += " ORDER BY id DESC"

    connection = get_connection()
    try:
        rows = connection.execute(query, values).fetchall()
        users = [_user_from_row(row) for row in rows]
        # Добавляем количество доступных схем — полезно в таблице
        for user in users:
            user["library_count"] = connection.execute(
                "SELECT COUNT(*) AS total FROM user_entitlements "
                "WHERE user_id = ? AND revoked_at IS NULL",
                (user["id"],),
            ).fetchone()["total"]
        return users
    finally:
        connection.close()


def count_users():
    """Сколько покупателей зарегистрировано (без удалённых)."""
    connection = get_connection()
    try:
        return connection.execute(
            "SELECT COUNT(*) AS total FROM users WHERE deleted_at IS NULL"
        ).fetchone()["total"]
    finally:
        connection.close()


def public_display_name(user):
    """
    Выбирает публичное имя покупателя по его настройке.

    Правила (важно для приватности):
      * full     — имя и фамилия, если покупатель указал их сам;
      * nickname — никнейм;
      * first    — только имя;
      * свой вариант (display_name_custom) — если введён.

    Регистрационный email здесь НИКОГДА не используется.
    """
    if user is None:
        return ""

    custom = (user.get("display_name_custom") or "").strip()
    if custom:
        return custom[:config.DISPLAY_NAME_MAX_LENGTH]

    mode = (user.get("display_name_mode") or "first").strip()
    nickname = (user.get("nickname") or "").strip()
    name = (user.get("name") or "").strip()

    if mode == "full" and name:
        return name[:config.DISPLAY_NAME_MAX_LENGTH]
    if mode == "nickname" and nickname:
        return nickname[:config.DISPLAY_NAME_MAX_LENGTH]
    # По умолчанию — только имя (первое слово), это безопаснее всего
    if name:
        return name.split()[0][:config.DISPLAY_NAME_MAX_LENGTH]
    if nickname:
        return nickname[:config.DISPLAY_NAME_MAX_LENGTH]
    return "Рукодельница"


def delete_user(user_id):
    """Мягко удаляет аккаунт покупателя (можно вернуть обратно)."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE users SET deleted_at = ?, updated_at = ? WHERE id = ?",
            (_now(), _now(), user_id),
        )
        connection.commit()
    finally:
        connection.close()


def restore_user(user_id):
    """Возвращает мягко удалённый аккаунт."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE users SET deleted_at = NULL, updated_at = ? WHERE id = ?",
            (_now(), user_id),
        )
        connection.commit()
    finally:
        connection.close()


# --------------------------------------------------------------------------
# ТОКЕНЫ ПОДТВЕРЖДЕНИЯ ПОЧТЫ И СБРОСА ПАРОЛЯ
# --------------------------------------------------------------------------

def create_user_token(user_id, token_hash, purpose, expires_at):
    """Записывает токен (хранится только его хеш)."""
    connection = get_connection()
    try:
        connection.execute(
            "INSERT INTO user_tokens (user_id, token_hash, purpose, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, token_hash, purpose, expires_at, _now()),
        )
        connection.commit()
    finally:
        connection.close()


def find_user_token(token_hash, purpose):
    """
    Находит действующий (неиспользованный и не истёкший) токен.
    Возвращает словарь или None.
    """
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM user_tokens WHERE token_hash = ? AND purpose = ? "
            "AND used_at IS NULL AND expires_at > ? ORDER BY id DESC LIMIT 1",
            (token_hash, purpose, _now()),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "purpose": row["purpose"],
            "expires_at": row["expires_at"],
        }
    finally:
        connection.close()


def use_user_token(token_id):
    """Помечает токен использованным (повторно он не сработает)."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE user_tokens SET used_at = ? WHERE id = ?", (_now(), token_id)
        )
        connection.commit()
    finally:
        connection.close()


def invalidate_user_tokens(user_id, purpose=None):
    """Обнуляет все действующие токены покупателя (например, перед новым)."""
    connection = get_connection()
    try:
        if purpose:
            connection.execute(
                "UPDATE user_tokens SET used_at = ? "
                "WHERE user_id = ? AND purpose = ? AND used_at IS NULL",
                (_now(), user_id, purpose),
            )
        else:
            connection.execute(
                "UPDATE user_tokens SET used_at = ? "
                "WHERE user_id = ? AND used_at IS NULL",
                (_now(), user_id),
            )
        connection.commit()
    finally:
        connection.close()


def add_user_login_attempt(email, ip, success):
    """Записывает попытку входа покупателя."""
    connection = get_connection()
    try:
        connection.execute(
            "INSERT INTO user_login_attempts (email, ip, success, attempted_at) "
            "VALUES (?, ?, ?, ?)",
            (email or "", ip or "", 1 if success else 0, _now()),
        )
        connection.commit()
    finally:
        connection.close()


def recent_failed_user_attempts(ip, minutes=15):
    """Сколько раз за последние минуты пароль покупателя вводился неверно."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM user_login_attempts "
            "WHERE ip = ? AND success = 0 "
            "AND attempted_at > datetime('now', 'localtime', ?)",
            (ip or "", f"-{int(minutes)} minutes"),
        ).fetchone()
        return row["total"]
    finally:
        connection.close()


def clear_user_login_attempts(ip):
    """Очищает неудачные попытки входа покупателя с адреса."""
    connection = get_connection()
    try:
        connection.execute(
            "DELETE FROM user_login_attempts WHERE ip = ? AND success = 0",
            (ip or "",),
        )
        connection.commit()
    finally:
        connection.close()


# --------------------------------------------------------------------------
# ЦИФРОВЫЕ ФАЙЛЫ СХЕМ
# --------------------------------------------------------------------------

def _pattern_file_from_row(row):
    return {
        "id": row["id"],
        "pattern_id": row["pattern_id"],
        "format": row["format"],
        "title": row["title"],
        "stored_name": row["stored_name"],
        "original_name": row["original_name"],
        "size_bytes": row["size_bytes"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


def add_pattern_file(pattern_id, format_name, stored_name, title="",
                     original_name="", size_bytes=0):
    """Добавляет файл схемы. Возвращает id записи."""
    connection = get_connection()
    try:
        cursor = connection.execute(
            "INSERT INTO pattern_files "
            "(pattern_id, format, title, stored_name, original_name, size_bytes, "
            " is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (
                pattern_id, format_name, title, stored_name,
                original_name, int(size_bytes or 0), _now(),
            ),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def list_pattern_files(pattern_id, only_active=False):
    """Файлы схемы (для админки — все, для покупателя — только активные)."""
    connection = get_connection()
    try:
        query = "SELECT * FROM pattern_files WHERE pattern_id = ?"
        if only_active:
            query += " AND is_active = 1"
        query += " ORDER BY id"
        rows = connection.execute(query, (pattern_id,)).fetchall()
        return [_pattern_file_from_row(row) for row in rows]
    finally:
        connection.close()


def get_pattern_file(file_id):
    """Один файл схемы по id."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM pattern_files WHERE id = ?", (file_id,)
        ).fetchone()
        return _pattern_file_from_row(row) if row else None
    finally:
        connection.close()


def set_pattern_file_active(file_id, active):
    """Включает или отключает файл."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE pattern_files SET is_active = ? WHERE id = ?",
            (1 if active else 0, file_id),
        )
        connection.commit()
    finally:
        connection.close()


def delete_pattern_file(file_id):
    """Удаляет запись о файле. Сам файл удаляется отдельно (см. файловый код)."""
    connection = get_connection()
    try:
        connection.execute("DELETE FROM pattern_files WHERE id = ?", (file_id,))
        connection.commit()
    finally:
        connection.close()


# --------------------------------------------------------------------------
# ЗАКАЗЫ
# --------------------------------------------------------------------------

def _next_order_number(connection):
    """Придумывает следующий номер заказа: EK-2026-0001."""
    year = datetime.now().year
    row = connection.execute(
        "SELECT COUNT(*) AS total FROM orders WHERE order_number LIKE ?",
        (f"EK-{year}-%",),
    ).fetchone()
    return f"EK-{year}-{row['total'] + 1:04d}"


def create_order(user_id, items, note="", total=None, source="manual"):
    """
    Создаёт заказ вручную (например, покупка была на другой площадке).

    items — список словарей: {"pattern_id": 1, "title": "...", "price": 0}.

    Возвращает (order_id, order_number).
    """
    moment = _now()
    connection = get_connection()
    try:
        number = _next_order_number(connection)
        if total is None:
            total = sum(float(item.get("price") or 0) for item in items)
        cursor = connection.execute(
            "INSERT INTO orders "
            "(user_id, order_number, status, total, currency, note, source, "
            " created_at, updated_at) VALUES (?, ?, 'manual', ?, 'RUB', ?, ?, ?, ?)",
            (user_id, number, total, note, source, moment, moment),
        )
        order_id = cursor.lastrowid
        for item in items:
            connection.execute(
                "INSERT INTO order_items "
                "(order_id, pattern_id, title, price, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    order_id, item.get("pattern_id"),
                    item.get("title", ""), float(item.get("price") or 0), moment,
                ),
            )
        connection.commit()
        return order_id, number
    finally:
        connection.close()


def list_user_orders(user_id):
    """Заказы покупателя (сначала новые) вместе с позициями."""
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ).fetchall()
        orders = []
        for row in rows:
            order = {
                "id": row["id"],
                "order_number": row["order_number"],
                "status": row["status"],
                "total": row["total"],
                "currency": row["currency"],
                "note": row["note"],
                "source": row["source"],
                "created_at": row["created_at"],
            }
            order["order_items"] = [
                {
                    "title": item["title"],
                    "price": item["price"],
                    "pattern_id": item["pattern_id"],
                }
                for item in connection.execute(
                    "SELECT * FROM order_items WHERE order_id = ? ORDER BY id",
                    (row["id"],),
                ).fetchall()
            ]
            orders.append(order)
        return orders
    finally:
        connection.close()


def list_orders(search=""):
    """Все заказы для админ-панели, с именем покупателя."""
    connection = get_connection()
    try:
        query = """
        SELECT o.*, u.name AS user_name, u.email AS user_email
        FROM orders o LEFT JOIN users u ON u.id = o.user_id
        WHERE 1 = 1
        """
        values = []
        if search:
            query += " AND (o.order_number LIKE ? OR u.name LIKE ? OR u.email LIKE ?)"
            like = f"%{search}%"
            values.extend([like, like, like])
        query += " ORDER BY o.id DESC"
        rows = connection.execute(query, values).fetchall()
        orders = []
        for row in rows:
            order = dict(row)
            order["order_items"] = [
                dict(item) for item in connection.execute(
                    "SELECT * FROM order_items WHERE order_id = ? ORDER BY id",
                    (row["id"],),
                ).fetchall()
            ]
            orders.append(order)
        return orders
    finally:
        connection.close()


def count_orders():
    """Сколько всего заказов."""
    connection = get_connection()
    try:
        return connection.execute("SELECT COUNT(*) AS total FROM orders").fetchone()["total"]
    finally:
        connection.close()


def delete_order(order_id):
    """Удаляет заказ вместе с позициями. Права доступа при этом не трогаем."""
    connection = get_connection()
    try:
        connection.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        connection.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        connection.commit()
    finally:
        connection.close()


# --------------------------------------------------------------------------
# ПРАВА ДОСТУПА (БИБЛИОТЕКА)
# --------------------------------------------------------------------------

def grant_entitlement(user_id, pattern_id, order_id=None, granted_by="admin",
                      note="", source="manual"):
    """
    Выдаёт покупателю право скачивать схемы.
    Повторная выдача не создаёт дубликат и «оживляет» отозванное право.

    source='manual' — право выдал администратор (например, покупка была
    на другой площадке). Такое право НЕ даёт отметку «Покупка подтверждена»
    в отзывах. source='site' — покупка на нашем сайте (пока продажи
    онлайн не подключены, этот вариант зарезервирован для будущего).

    Возвращает id записи.
    """
    moment = _now()
    connection = get_connection()
    try:
        existing = connection.execute(
            "SELECT id FROM user_entitlements WHERE user_id = ? AND pattern_id = ?",
            (user_id, pattern_id),
        ).fetchone()
        if existing:
            connection.execute(
                "UPDATE user_entitlements SET revoked_at = NULL, granted_at = ?, "
                "order_id = COALESCE(?, order_id), granted_by = ?, source = ?, "
                "note = ? WHERE id = ?",
                (moment, order_id, granted_by, source, note, existing["id"]),
            )
            connection.commit()
            return existing["id"]
        cursor = connection.execute(
            "INSERT INTO user_entitlements "
            "(user_id, pattern_id, order_id, granted_at, granted_by, note, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, pattern_id, order_id, moment, granted_by, note, source),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def revoke_entitlement(user_id, pattern_id):
    """Отзывает право доступа (файлы снова недоступны покупателю)."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE user_entitlements SET revoked_at = ? "
            "WHERE user_id = ? AND pattern_id = ? AND revoked_at IS NULL",
            (_now(), user_id, pattern_id),
        )
        connection.commit()
    finally:
        connection.close()


def user_has_entitlement(user_id, pattern_id):
    """
    Есть ли у покупателя действующее право доступа к схеме.
    Это главная проверка перед скачиванием файла.
    """
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT 1 FROM user_entitlements "
            "WHERE user_id = ? AND pattern_id = ? AND revoked_at IS NULL",
            (user_id, pattern_id),
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def list_user_library(user_id):
    """
    Библиотека покупателя: схемы с действующим правом доступа,
    вместе с датой выдачи и списком доступных файлов.
    """
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT e.id AS entitlement_id, e.granted_at, e.pattern_id,
                   p.slug, p.title, p.description, p.main_image, p.is_published,
                   p.deleted_at AS pattern_deleted
            FROM user_entitlements e
            JOIN patterns p ON p.id = e.pattern_id
            WHERE e.user_id = ? AND e.revoked_at IS NULL
            ORDER BY e.granted_at DESC, e.id DESC
            """,
            (user_id,),
        ).fetchall()

        library = []
        for row in rows:
            files = [
                {
                    "id": file["id"],
                    "format": file["format"],
                    "title": file["title"],
                    "size_bytes": file["size_bytes"],
                }
                for file in connection.execute(
                    "SELECT * FROM pattern_files "
                    "WHERE pattern_id = ? AND is_active = 1 ORDER BY id",
                    (row["pattern_id"],),
                ).fetchall()
            ]
            library.append({
                "entitlement_id": row["entitlement_id"],
                "granted_at": row["granted_at"],
                "pattern_id": row["pattern_id"],
                "slug": row["slug"],
                "title": row["title"],
                "description": row["description"],
                "main_image": row["main_image"],
                "is_published": bool(row["is_published"]),
                "pattern_deleted": row["pattern_deleted"] is not None,
                "files": files,
            })
        return library
    finally:
        connection.close()


def list_entitlements(search=""):
    """Все права доступа для админ-панели (с именами покупателя и схемы)."""
    connection = get_connection()
    try:
        query = """
        SELECT e.*, u.name AS user_name, u.email AS user_email, p.title AS pattern_title,
               p.slug AS pattern_slug
        FROM user_entitlements e
        LEFT JOIN users u ON u.id = e.user_id
        LEFT JOIN patterns p ON p.id = e.pattern_id
        WHERE 1 = 1
        """
        values = []
        if search:
            query += " AND (u.name LIKE ? OR u.email LIKE ? OR p.title LIKE ?)"
            like = f"%{search}%"
            values.extend([like, like, like])
        query += " ORDER BY e.id DESC"
        return [dict(row) for row in connection.execute(query, values).fetchall()]
    finally:
        connection.close()


# --------------------------------------------------------------------------
# ГОТОВЫЕ РАБОТЫ (ОТШИВЫ)
# --------------------------------------------------------------------------

def _project_from_row(row):
    keys = row.keys()
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "pattern_id": row["pattern_id"],
        "story": row["story"],
        "display_name": row["display_name"],
        "status": row["status"],
        "moderation_note": row["moderation_note"],
        "owns_photos": bool(row["owns_photos"]),
        "publish_consent": bool(row["publish_consent"]),
        "show_on_home": bool(row["show_on_home"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "approved_at": row["approved_at"],
        "user_name": row["user_name"] if "user_name" in keys else "",
        "user_email": row["user_email"] if "user_email" in keys else "",
        "pattern_title": row["pattern_title"] if "pattern_title" in keys else "",
        "pattern_slug": row["pattern_slug"] if "pattern_slug" in keys else "",
    }


_PROJECT_SELECT = """
SELECT fp.*, u.name AS user_name, u.email AS user_email,
       p.title AS pattern_title, p.slug AS pattern_slug
FROM finished_projects fp
LEFT JOIN users u ON u.id = fp.user_id
LEFT JOIN patterns p ON p.id = fp.pattern_id
"""


def create_finished_project(user_id, pattern_id, story, display_name,
                            owns_photos, publish_consent):
    """Создаёт отшив со статусом «ожидает проверки». Возвращает id."""
    moment = _now()
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO finished_projects (
                user_id, pattern_id, story, display_name, status,
                owns_photos, publish_consent, show_on_home, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?, 1, ?, ?)
            """,
            (
                user_id, pattern_id, story, display_name,
                1 if owns_photos else 0, 1 if publish_consent else 0, moment, moment,
            ),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def add_project_image(project_id, stored_path, position=0):
    """Добавляет фотографию к отшиву."""
    connection = get_connection()
    try:
        connection.execute(
            "INSERT INTO finished_project_images (project_id, stored_path, position, created_at) "
            "VALUES (?, ?, ?, ?)",
            (project_id, stored_path, position, _now()),
        )
        connection.commit()
    finally:
        connection.close()


def update_project_image(image_id, stored_path):
    """
    Меняет путь фотографии отшива.

    Используется при публикации: вместо оригинала (в защищённой папке)
    записывается путь к оптимизированной копии для сайта.
    """
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE finished_project_images SET stored_path = ? WHERE id = ?",
            (stored_path, image_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_project_images(project_id):
    """Пути фотографий отшива по порядку."""
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT id, stored_path FROM finished_project_images "
            "WHERE project_id = ? ORDER BY position, id",
            (project_id,),
        ).fetchall()
        return [{"id": row["id"], "path": row["stored_path"]} for row in rows]
    finally:
        connection.close()


def get_project(project_id):
    """Один отшив по id."""
    connection = get_connection()
    try:
        row = connection.execute(
            _PROJECT_SELECT + " WHERE fp.id = ?", (project_id,)
        ).fetchone()
        return _project_from_row(row) if row else None
    finally:
        connection.close()


def list_projects(status="", user_id=None, search="", limit=None):
    """Список отшивов (для админки и для личного кабинета)."""
    query = _PROJECT_SELECT + " WHERE 1 = 1"
    values = []
    if status:
        query += " AND fp.status = ?"
        values.append(status)
    if user_id:
        query += " AND fp.user_id = ?"
        values.append(user_id)
    if search:
        query += " AND (fp.display_name LIKE ? OR fp.story LIKE ? OR p.title LIKE ?)"
        like = f"%{search}%"
        values.extend([like, like, like])
    query += " ORDER BY fp.id DESC"
    if limit:
        query += f" LIMIT {int(limit)}"

    connection = get_connection()
    try:
        return [_project_from_row(row) for row in connection.execute(query, values).fetchall()]
    finally:
        connection.close()


def list_public_projects(limit=None):
    """
    Отшивы для публичной галереи: одобренные, с согласием на публикацию,
    разрешённые к показу на главной.
    """
    query = """
    SELECT fp.*, p.title AS pattern_title, p.slug AS pattern_slug
    FROM finished_projects fp
    LEFT JOIN patterns p ON p.id = fp.pattern_id
    WHERE fp.status = 'approved' AND fp.publish_consent = 1
      AND fp.show_on_home = 1
    ORDER BY fp.approved_at DESC, fp.id DESC
    """
    if limit:
        query += f" LIMIT {int(limit)}"

    connection = get_connection()
    try:
        projects = []
        for row in connection.execute(query).fetchall():
            project = _project_from_row(row)
            project["images"] = [
                img["stored_path"] for img in connection.execute(
                    "SELECT stored_path FROM finished_project_images "
                    "WHERE project_id = ? ORDER BY position, id",
                    (row["id"],),
                ).fetchall()
            ]
            projects.append(project)
        return projects
    finally:
        connection.close()


def set_project_status(project_id, status, note="", show_on_home=None):
    """Меняет статус отшива (одобрить/отклонить/скрыть/снять)."""
    connection = get_connection()
    try:
        fields = ["status = ?", "moderation_note = ?", "updated_at = ?"]
        values = [status, note, _now()]
        if status == "approved":
            fields.append("approved_at = ?")
            values.append(_now())
        if show_on_home is not None:
            fields.append("show_on_home = ?")
            values.append(1 if show_on_home else 0)
        values.append(project_id)
        connection.execute(
            f"UPDATE finished_projects SET {', '.join(fields)} WHERE id = ?", values
        )
        connection.commit()
    finally:
        connection.close()


def set_project_show_on_home(project_id, show):
    """Показывать ли работу на главной странице."""
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE finished_projects SET show_on_home = ?, updated_at = ? WHERE id = ?",
            (1 if show else 0, _now(), project_id),
        )
        connection.commit()
    finally:
        connection.close()


def set_project_consent(project_id, consent):
    """
    Меняет согласие покупателя на публикацию.
    Отзыв согласия автоматически снимает работу с публичного показа.
    """
    connection = get_connection()
    try:
        if consent:
            connection.execute(
                "UPDATE finished_projects SET publish_consent = 1, updated_at = ? "
                "WHERE id = ?",
                (_now(), project_id),
            )
        else:
            # Согласие отозвано — материал сразу уходит с публичного доступа
            connection.execute(
                "UPDATE finished_projects SET publish_consent = 0, "
                "show_on_home = 0, status = 'withdrawn', updated_at = ? WHERE id = ?",
                (_now(), project_id),
            )
        connection.commit()
    finally:
        connection.close()


def delete_project(project_id):
    """Удаляет отшив вместе с записями о его фотографиях."""
    connection = get_connection()
    try:
        connection.execute(
            "DELETE FROM finished_project_images WHERE project_id = ?", (project_id,)
        )
        connection.execute("DELETE FROM finished_projects WHERE id = ?", (project_id,))
        connection.commit()
    finally:
        connection.close()


def count_projects_by_status():
    """Сколько отшивов в каждом статусе (для сводки админки)."""
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS total FROM finished_projects GROUP BY status"
        ).fetchall()
        result = {"pending": 0, "approved": 0, "rejected": 0, "hidden": 0, "withdrawn": 0}
        for row in rows:
            result[row["status"]] = row["total"]
        return result
    finally:
        connection.close()


# --------------------------------------------------------------------------
# ОТЗЫВЫ
# --------------------------------------------------------------------------

def _review_from_row(row):
    keys = row.keys()
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "pattern_id": row["pattern_id"],
        "category": row["category"],
        "rating": row["rating"],
        "text": row["text"],
        "photo_path": row["photo_path"],
        "display_name": row["display_name"],
        "status": row["status"],
        "moderation_note": row["moderation_note"],
        "verified_purchase": bool(row["verified_purchase"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "approved_at": row["approved_at"],
        "user_name": row["user_name"] if "user_name" in keys else "",
        "user_email": row["user_email"] if "user_email" in keys else "",
        "pattern_title": row["pattern_title"] if "pattern_title" in keys else "",
        "pattern_slug": row["pattern_slug"] if "pattern_slug" in keys else "",
    }


_REVIEW_SELECT = """
SELECT r.*, u.name AS user_name, u.email AS user_email,
       p.title AS pattern_title, p.slug AS pattern_slug
FROM reviews r
LEFT JOIN users u ON u.id = r.user_id
LEFT JOIN patterns p ON p.id = r.pattern_id
"""


def create_review(user_id, text, rating, display_name, category="pattern",
                  pattern_id=None, photo_path="", verified_purchase=False,
                  content_hash=""):
    """Создаёт отзыв со статусом «ожидает проверки». Возвращает id."""
    moment = _now()
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO reviews (
                user_id, pattern_id, category, rating, text, photo_path,
                display_name, status, verified_purchase, content_hash,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (
                user_id, pattern_id, category, int(rating), text, photo_path,
                display_name, 1 if verified_purchase else 0, content_hash,
                moment, moment,
            ),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def get_review(review_id):
    """Один отзыв по id."""
    connection = get_connection()
    try:
        row = connection.execute(
            _REVIEW_SELECT + " WHERE r.id = ?", (review_id,)
        ).fetchone()
        return _review_from_row(row) if row else None
    finally:
        connection.close()


def list_user_reviews(user_id):
    """Отзывы покупателя (со статусами), сначала новые."""
    connection = get_connection()
    try:
        rows = connection.execute(
            _REVIEW_SELECT + " WHERE r.user_id = ? ORDER BY r.id DESC", (user_id,)
        ).fetchall()
        return [_review_from_row(row) for row in rows]
    finally:
        connection.close()


def list_reviews(status="", category="", pattern_id=None, user_id=None, limit=None):
    """Список отзывов для админки и публичных страниц."""
    query = _REVIEW_SELECT + " WHERE 1 = 1"
    values = []
    if status:
        query += " AND r.status = ?"
        values.append(status)
    if category:
        query += " AND r.category = ?"
        values.append(category)
    if pattern_id:
        query += " AND r.pattern_id = ?"
        values.append(pattern_id)
    if user_id:
        query += " AND r.user_id = ?"
        values.append(user_id)
    query += " ORDER BY r.approved_at DESC, r.id DESC"
    if limit:
        query += f" LIMIT {int(limit)}"

    connection = get_connection()
    try:
        return [_review_from_row(row) for row in connection.execute(query, values).fetchall()]
    finally:
        connection.close()


def count_reviews_by_status():
    """Сколько отзывов в каждом статусе (для сводки админки)."""
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS total FROM reviews GROUP BY status"
        ).fetchall()
        result = {"pending": 0, "approved": 0, "rejected": 0, "hidden": 0}
        for row in rows:
            result[row["status"]] = row["total"]
        return result
    finally:
        connection.close()


def set_review_status(review_id, status, note=""):
    """Меняет статус отзыва (одобрить/отклонить/скрыть)."""
    connection = get_connection()
    try:
        fields = ["status = ?", "moderation_note = ?", "updated_at = ?"]
        values = [status, note, _now()]
        if status == "approved":
            fields.append("approved_at = ?")
            values.append(_now())
        values.append(review_id)
        connection.execute(
            f"UPDATE reviews SET {', '.join(fields)} WHERE id = ?", values
        )
        connection.commit()
    finally:
        connection.close()


def delete_review(review_id):
    """Удаляет отзыв (например, спам)."""
    connection = get_connection()
    try:
        connection.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        connection.commit()
    finally:
        connection.close()


def count_identical_reviews(user_id, content_hash):
    """Сколько раз этот покупатель отправлял отзыв с тем же текстом."""
    connection = get_connection()
    try:
        return connection.execute(
            "SELECT COUNT(*) AS total FROM reviews "
            "WHERE user_id = ? AND content_hash = ?",
            (user_id, content_hash),
        ).fetchone()["total"]
    finally:
        connection.close()


def review_rating_stats(pattern_id=None):
    """
    Средний рейтинг и число отзывов. Учитываются ТОЛЬКО опубликованные
    (status = 'approved') отзывы. Если отзывов нет — возвращаем None,
    чтобы сайт не показывал выдуманный рейтинг.
    """
    connection = get_connection()
    try:
        query = "SELECT COUNT(*) AS total, AVG(rating) AS avg FROM reviews WHERE status = 'approved'"
        values = []
        if pattern_id:
            query += " AND pattern_id = ?"
            values.append(pattern_id)
        row = connection.execute(query, values).fetchone()
        if not row["total"]:
            return {"count": 0, "average": None}
        return {"count": row["total"], "average": round(row["avg"], 1)}
    finally:
        connection.close()


def has_verified_purchase(user_id, pattern_id):
    """
    Куплена ли схема покупателем именно на нашем сайте.

    Отметку «Покупка подтверждена» получают только покупки, сделанные
    здесь: право с источником 'site'. Если доступ выдал администратор
    вручную (покупка на другой площадке), отметки НЕ будет — сайт не
    выдаёт чужую покупку за свою.
    """
    if not pattern_id:
        return False
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT 1 FROM user_entitlements "
            "WHERE user_id = ? AND pattern_id = ? AND revoked_at IS NULL "
            "AND source = 'site' LIMIT 1",
            (user_id, pattern_id),
        ).fetchone()
        return row is not None
    finally:
        connection.close()


# --------------------------------------------------------------------------
# ЖУРНАЛ МОДЕРАЦИИ
# --------------------------------------------------------------------------

def log_moderation(target_type, target_id, action, reason="", admin_name=""):
    """Записывает действие модератора в журнал."""
    connection = get_connection()
    try:
        connection.execute(
            "INSERT INTO moderation_actions "
            "(target_type, target_id, action, reason, admin_name, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (target_type, target_id, action, reason or "", admin_name or "", _now()),
        )
        connection.commit()
    finally:
        connection.close()


def list_moderation_actions(target_type=None, target_id=None, limit=50):
    """История модерации (последние действия)."""
    query = "SELECT * FROM moderation_actions WHERE 1 = 1"
    values = []
    if target_type:
        query += " AND target_type = ?"
        values.append(target_type)
    if target_id:
        query += " AND target_id = ?"
        values.append(target_id)
    query += " ORDER BY id DESC"
    if limit:
        query += f" LIMIT {int(limit)}"

    connection = get_connection()
    try:
        return [dict(row) for row in connection.execute(query, values).fetchall()]
    finally:
        connection.close()


# --------------------------------------------------------------------------
# РЕЗЕРВНОЕ КОПИРОВАНИЕ
# --------------------------------------------------------------------------

def backup_database():
    """
    Создаёт копию базы данных в папке data/backups/.
    Возвращает путь к копии (или None, если базы ещё нет).
    """
    if not os.path.isfile(config.DB_PATH):
        return None
    backup_dir = config.BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = os.path.join(backup_dir, f"catalog_{stamp}.db")

    # Соединение открываем/закрываем, чтобы все данные точно попали в файл
    connection = get_connection()
    try:
        connection.commit()
    finally:
        connection.close()

    shutil.copy2(config.DB_PATH, target)
    return target


def list_backups():
    """Список созданных резервных копий (сначала новые)."""
    backup_dir = config.BACKUP_DIR
    if not os.path.isdir(backup_dir):
        return []
    files = [
        name for name in os.listdir(backup_dir)
        if name.startswith("catalog_") and name.endswith(".db")
    ]
    files.sort(reverse=True)
    backups = []
    for name in files:
        full = os.path.join(backup_dir, name)
        backups.append({
            "name": name,
            "size_kb": round(os.path.getsize(full) / 1024, 1),
            "created": datetime.fromtimestamp(
                os.path.getmtime(full)
            ).strftime("%d.%m.%Y %H:%M"),
        })
    return backups
