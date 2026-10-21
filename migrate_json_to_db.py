# -*- coding: utf-8 -*-
"""
migrate_json_to_db.py — разовый перенос данных из patterns.json в базу SQLite.

Когда запускать:
    один раз, при переходе на новую версию сайта с админ-панелью.

Как запускать (из папки проекта):
    python migrate_json_to_db.py

Что делает команда:

1. Делает резервную копию исходного файла data/patterns.json
   (копия кладётся рядом: data/patterns.backup-ГГГГ-ММ-ДД_ЧЧ-ММ-СС.json).

2. Читает схемы из JSON и добавляет их в базу.

3. СОХРАНЯЕТ прежние id схем. Это важно: корзины покупателей
   в браузерах хранят именно id, и после переноса они продолжают работать.

4. Пропускает схемы, которые уже есть в базе (совпадение по id или названию),
   поэтому повторный запуск команды ничего не дублирует и не ломает.

5. Создаёт категории из поля category у схем и раскладывает схемы по ним.

6. Создаёт пару чувствительных схем в «черновиках» (если они были скрыты
   флагом is_active: false), чтобы автор мог их проверить и опубликовать.

Тексты сайта из site_content.json переносятся отдельно — они попадают
в таблицу site_settings (см. функцию import_site_content ниже).
"""

import json
import os
import shutil
import sys
from datetime import datetime

import config
import database
from security import verify_password  # noqa: F401  (нужен для проверок окружения)


def backup_source_json():
    """Создаёт копию patterns.json — на случай, если что-то пойдёт не так."""
    if not os.path.isfile(config.PATTERNS_JSON):
        return None
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = os.path.join(
        config.DATA_DIR, f"patterns.backup-{stamp}.json"
    )
    shutil.copy2(config.PATTERNS_JSON, target)
    return target


def read_patterns_json():
    """Читает список схем из JSON-файла."""
    if not os.path.isfile(config.PATTERNS_JSON):
        return []
    with open(config.PATTERNS_JSON, encoding="utf-8") as file:
        data = json.load(file)
    return data.get("patterns", [])


def read_site_content_json():
    """Читает тексты сайта из JSON-файла."""
    if not os.path.isfile(config.SITE_CONTENT_JSON):
        return {}
    with open(config.SITE_CONTENT_JSON, encoding="utf-8") as file:
        return json.load(file)


def import_categories(patterns):
    """
    Создаёт категории по значениям поля category у схем.
    Возвращает словарь {название категории: id в базе}.
    """
    known = {}
    for category in database.list_categories():
        known[category["name"].lower()] = category["id"]

    created = 0
    for pattern in patterns:
        name = (pattern.get("category") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in known:
            continue
        # Не создаём категорию, если по этому названию уже есть удалённая
        existing = database.get_category_by_name(name)
        if existing:
            known[key] = existing["id"]
            continue
        known[key] = database.add_category(name)
        created += 1

    print(f"  Категорий создано: {created}")
    return known


def import_patterns(patterns, category_ids):
    """
    Переносит схемы в базу. Возвращает количество добавленных записей.

    Важно: id сохраняется прежним, чтобы корзины покупателей
    продолжали работать без изменений.
    """
    existing_ids = {p["id"] for p in database.list_patterns(include_deleted=True)}
    existing_titles = {
        p["title"].strip().lower()
        for p in database.list_patterns(include_deleted=True)
    }

    added = 0
    skipped = 0
    published = 0

    for item in patterns:
        title = (item.get("title") or "").strip()
        old_id = item.get("id")

        # Пропускаем дубликаты: по id или по названию
        if old_id in existing_ids or (title and title.lower() in existing_titles):
            skipped += 1
            continue

        category_name = (item.get("category") or "").strip()
        category_id = category_ids.get(category_name.lower()) if category_name else None

        size = item.get("size_stitches") or {}
        is_active = item.get("is_active", True)

        data = {
            "slug": item.get("slug") or database.slug_from_name(title),
            "title": title,
            "description": item.get("description", ""),
            "full_description": item.get("full_description", ""),
            "price": item.get("price", 0),
            "currency": item.get("currency", "RUB"),
            "category_id": category_id,
            "width": size.get("width"),
            "height": size.get("height"),
            "colors": item.get("colors"),
            "fabric": item.get("fabric", ""),
            "fabric_count": item.get("fabric_count"),
            "finished_size": "",
            "difficulty": item.get("difficulty", ""),
            "main_image": item.get("main_image", ""),
            "preview_10x10": item.get("preview_10x10", ""),
        }

        # Сохраняем прежний id: корзины хранят именно его.
        # is_active: false → черновик (не покажется в каталоге, пока
        # администратор сам не опубликует схему).
        pattern_id = _insert_with_id(data, old_id, publish=bool(is_active))
        if is_active:
            published += 1

        # Дополнительные фотографии
        gallery = item.get("gallery") or []
        if gallery:
            database.update_pattern(pattern_id, {}, images=gallery, publish=None)

        added += 1

    print(f"  Схем перенесено: {added} (опубликовано: {published}, пропущено как дубликаты: {skipped})")
    return added


def _insert_with_id(data, wanted_id, publish):
    """
    Создаёт схему, стараясь сохранить прежний id.

    Если такой id уже занят (такое возможно при повторном импорте),
    создаётся запись с новым автоматическим id — данные не теряются.
    """
    connection = database.get_connection()
    try:
        # Проверяем, свободен ли нужный id
        taken = connection.execute(
            "SELECT id FROM patterns WHERE id = ?", (wanted_id,)
        ).fetchone() is not None
    finally:
        connection.close()

    if taken or not wanted_id:
        return database.create_pattern(data, publish=publish)

    moment = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    connection = database.get_connection()
    try:
        connection.execute(
            """
            INSERT INTO patterns (
                id, slug, title, description, full_description, price, currency,
                category_id, width, height, colors, fabric, fabric_count,
                finished_size, difficulty, main_image, preview_10x10,
                is_published, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                wanted_id, data["slug"], data["title"], data["description"],
                data["full_description"], data["price"], data["currency"],
                data["category_id"], data["width"], data["height"], data["colors"],
                data["fabric"], data["fabric_count"], data["finished_size"],
                data["difficulty"], data["main_image"], data["preview_10x10"],
                1 if publish else 0, moment, moment,
            ),
        )
        connection.commit()
        return wanted_id
    finally:
        connection.close()


def import_site_content(content):
    """Переносит тексты сайта из site_content.json в таблицу настроек."""
    if not content:
        print("  Тексты сайта: файл не найден, оставляю значения по умолчанию.")
        return

    values = {}
    hero = content.get("hero") or {}
    if hero.get("title"):
        values["hero_title"] = hero["title"]
    if hero.get("subtitle"):
        values["hero_subtitle"] = hero["subtitle"]
    if hero.get("button_text"):
        values["hero_button"] = hero["button_text"]

    about = content.get("about") or {}
    if about.get("title"):
        values["about_title"] = about["title"]
    if about.get("text"):
        values["about_text"] = about["text"]

    if content.get("catalog_title"):
        values["catalog_title"] = content["catalog_title"]

    preview = content.get("preview_block") or {}
    if preview.get("title"):
        values["preview_title"] = preview["title"]
    if preview.get("subtitle"):
        values["preview_subtitle"] = preview["subtitle"]
    if preview.get("empty_message"):
        values["preview_empty_message"] = preview["empty_message"]

    # Авторские тексты (hero, about) переносим только если они ещё стандартные
    current = database.get_settings()
    for key, value in values.items():
        # Не перезаписываем то, что администратор уже менял в панели
        if key in ("hero_title", "hero_subtitle", "about_text") and current.get(key):
            continue
        database.set_setting(key, value)

    # Название и подзаголовок сайта
    if content.get("brand_name"):
        database.set_setting("site_name", content["brand_name"])
    if content.get("brand_tagline"):
        database.set_setting("site_tagline", content["brand_tagline"])
    if content.get("slogan"):
        database.set_setting("slogan", content["slogan"])

    print(f"  Текстов сайта перенесено: {len(values)}")


def main():
    print("=" * 70)
    print("ПЕРЕНОС ДАННЫХ ИЗ JSON В БАЗУ ДАННЫХ SQLITE")
    print("=" * 70)
    print(f"База данных: {config.DB_PATH}")
    print()

    # 1. Готовим базу
    print("1. Создаю таблицы базы (существующие данные не трогаю)...")
    database.init_db()

    already = database.count_patterns(include_deleted=True)
    if already:
        print(f"   В базе уже есть схемы: {already}.")
        print("   Будут добавлены только отсутствующие — дубликатов не появится.")
    print()

    # 2. Резервная копия исходного JSON
    print("2. Делаю резервную копию файла patterns.json...")
    backup = backup_source_json()
    if backup:
        print(f"   Копия сохранена: {os.path.basename(backup)}")
    else:
        print("   Файл patterns.json не найден — нечего копировать.")
    print()

    # 3. Читаем JSON
    print("3. Читаю схемы из patterns.json...")
    patterns = read_patterns_json()
    print(f"   Найдено записей: {len(patterns)}")
    print()

    # 4. Категории
    print("4. Переношу категории...")
    category_ids = import_categories(patterns)
    print()

    # 5. Схемы
    print("5. Переношу схемы...")
    import_patterns(patterns, category_ids)
    print()

    # 6. Тексты сайта
    print("6. Переношу тексты сайта...")
    import_site_content(read_site_content_json())
    print()

    # 7. Резервная копия базы
    print("7. Делаю резервную копию базы...")
    backup = database.backup_database()
    print(f"   Копия: {os.path.basename(backup) if backup else 'база пустая'}")
    print()

    status = database.count_by_status()
    print("=" * 70)
    print("ГОТОВО!")
    print(f"  Всего схем в базе: {database.count_patterns()}")
    print(f"  Опубликовано: {status['published']}")
    print(f"  Черновиков: {status['draft']}")
    print(f"  Категорий: {len(database.list_categories())}")
    print()
    print("Дальше:")
    print("  1. Один раз задайте пароль администратора:  python setup_admin.py")
    print("  2. Запустите сайт:                          python app.py")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # понятное сообщение вместо длинной трассировки
        print()
        print("!" * 70)
        print("НЕ УДАЛОСЬ ЗАВЕРШИТЬ ПЕРЕНОС ДАННЫХ")
        print(f"Причина: {error}")
        print("Исходные файлы не изменялись — данные в безопасности.")
        print("Исправьте ошибку и запустите команду снова.")
        print("!" * 70)
        sys.exit(1)
