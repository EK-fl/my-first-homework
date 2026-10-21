# -*- coding: utf-8 -*-
"""
security.py — всё, что связано с безопасностью сайта.

Здесь собраны четыре важные вещи:

1. Хеширование пароля администратора
   (пароль никогда не хранится в открытом виде).

2. Защита форм от CSRF-атак
   (чужой сайт не сможет отправить форму от имени администратора).

3. Ограничение попыток входа
   (перебрать пароль подбором не получится).

4. Проверка загружаемых изображений
   (по расширению, размеру и РЕАЛЬНОМУ содержимому файла).

Комментарии написаны простым языком, чтобы файл можно было читать
как учебник.
"""

import os
import re
import secrets
import hashlib
import hmac

from werkzeug.security import check_password_hash, generate_password_hash

import config

# --------------------------------------------------------------------------
# 1. ПАРОЛЬ АДМИНИСТРАТОРА
# --------------------------------------------------------------------------

# Минимальная длина пароля для команды setup_admin.py
MIN_PASSWORD_LENGTH = 8


def hash_password(password):
    """
    Превращает пароль в хеш — длинную строку, из которой нельзя
    восстановить сам пароль.

    method="scrypt" — современный устойчивый алгоритм, он входит в состав
    Werkzeug (часть Flask), поэтому ничего дополнительно ставить не нужно.
    """
    return generate_password_hash(password, method="scrypt")


def verify_password(password_hash, password):
    """
    Проверяет, подходит ли введённый пароль к сохранённому хешу.
    Возвращает True или False.
    """
    if not password_hash or not password:
        return False
    try:
        return check_password_hash(password_hash, password)
    except (ValueError, TypeError):
        # Повреждённый хеш в базе не должен ломать страницу входа
        return False


def password_problems(password):
    """
    Возвращает список замечаний к паролю.
    Пустой список = пароль хороший.
    """
    problems = []
    if len(password or "") < MIN_PASSWORD_LENGTH:
        problems.append(f"пароль короче {MIN_PASSWORD_LENGTH} символов")
    if password and password.isdigit():
        problems.append("пароль состоит только из цифр")
    if password and password.lower() in {"password", "qwerty", "12345678", "admin123"}:
        problems.append("слишком простой пароль")
    return problems


# --------------------------------------------------------------------------
# 2. ЗАЩИТА ОТ CSRF
# --------------------------------------------------------------------------
# CSRF — это когда чужой сайт тайком отправляет форму на наш сайт,
# пользуясь тем, что администратор уже вошёл в панель.
# Защита проста: в каждую форму добавляем «секретный токен», который
# знает только наш сервер. Чужая форма его не подставит.

def make_csrf_token():
    """Создаёт случайный токен для формы (32 байта случайности)."""
    return secrets.token_urlsafe(32)


def tokens_match(expected, received):
    """
    Сравнивает токены безопасно.

    secrets.compare_digest сравнивает строки за одинаковое время —
    так злоумышленник не сможет подобрать токен по времени ответа.
    """
    if not expected or not received:
        return False
    return secrets.compare_digest(str(expected), str(received))


# --------------------------------------------------------------------------
# 3. ОГРАНИЧЕНИЕ ПОПЫТОК ВХОДА
# --------------------------------------------------------------------------

def login_is_blocked(failed_attempts):
    """
    Проверяет, не слишком ли много было неудачных попыток.
    Возвращает True, если вход временно заблокирован.
    """
    return failed_attempts >= config.LOGIN_MAX_ATTEMPTS


def attempts_left(failed_attempts):
    """Сколько попыток осталось до временной блокировки."""
    return max(0, config.LOGIN_MAX_ATTEMPTS - failed_attempts)


# --------------------------------------------------------------------------
# 4. ПРОВЕРКА ЗАГРУЖАЕМЫХ ФАЙЛОВ
# --------------------------------------------------------------------------
# Требование: проверять тип, размер и реальное содержимое.
# Мы не доверяем ни имени файла, ни тому, что написал браузер.
# Поэтому читаем начало файла («магические байты») и смотрим,
# действительно ли это картинка. Исполняемые файлы (.exe, .sh, .php...)
# отбрасываются сразу.

# Разрешённые расширения и то, с каких байтов начинается настоящий файл
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}

# Расширения, которые опасны, потому что могут выполниться на сервере
FORBIDDEN_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".dll", ".sys",
    ".sh", ".bash", ".ps1", ".py", ".pyc", ".pyo", ".rb", ".pl", ".php",
    ".php3", ".php4", ".php5", ".phtml", ".asp", ".aspx", ".jsp", ".jspx",
    ".cgi", ".jar", ".js", ".mjs", ".vbs", ".wsf", ".hta", ".reg",
}

# «Магические байты» — подпись в начале реального файла
_MAGIC_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),  # у WEBP после RIFF идут 4 байта и "WEBP"
)


class UploadError(Exception):
    """Понятная ошибка при загрузке файла — показывается администратору."""


def _clean_filename(filename):
    """Оставляет от имени файла только безопасные символы."""
    filename = os.path.basename(filename or "").replace("\\", "/")
    filename = filename.split("/")[-1]
    return filename


def safe_upload_name(filename, prefix=""):
    """
    Делает из имени загруженного файла безопасное имя:
    только латиница, цифры, дефис и точка. Пробелы заменяются дефисом.
    """
    filename = _clean_filename(filename).lower()
    name, extension = os.path.splitext(filename)
    name = re.sub(r"[^a-z0-9\-]+", "-", name).strip("-") or "image"
    extension = re.sub(r"[^a-z0-9.]", "", extension)
    random_part = secrets.token_hex(4)  # 8 случайных символов
    if prefix:
        prefix = re.sub(r"[^a-z0-9\-]+", "-", prefix.lower()).strip("-") + "-"
    return f"{prefix}{name[:60]}-{random_part}{extension}"


def _looks_like_svg(data):
    """
    Проверяет, что файл действительно SVG, а не замаскированный скрипт.
    Внутри SVG не должно быть тегов script и опасных обработчиков.
    """
    try:
        text = data.decode("utf-8", errors="ignore").lower()
    except Exception:
        return False
    if "<svg" not in text:
        return False
    # Опасные конструкции: скрипты и обработчики событий
    dangerous = ("<script", "javascript:", "onload=", "onerror=", "<iframe", "<embed")
    return not any(item in text for item in dangerous)


def detect_image_type(data):
    """
    Определяет настоящий тип изображения по содержимому файла.
    Возвращает MIME-тип или None, если это не картинка.
    """
    for signature, mime in _MAGIC_SIGNATURES:
        if data.startswith(signature):
            # У WEBP после RIFF должны идти байты WEBP
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime
    # SVG — это текстовый файл, проверяем отдельно
    if _looks_like_svg(data):
        return "image/svg+xml"
    return None


def validate_image(storage, max_bytes=None):
    """
    Главная функция проверки загруженного файла.

    storage — объект файла из формы (request.files["main_image"]).
    Возвращает (данные_файла, mime-тип).

    Если с файлом что-то не так — выбрасывает UploadError с понятным
    русским текстом, который можно показать администратору.
    """
    if storage is None or not getattr(storage, "filename", ""):
        raise UploadError("Файл не выбран.")

    filename = _clean_filename(storage.filename)
    extension = os.path.splitext(filename)[1].lower()

    # --- Проверка 1: расширение ---
    if not extension:
        raise UploadError("У файла нет расширения. Назовите файл, например, shema.jpg")
    if extension in FORBIDDEN_EXTENSIONS:
        raise UploadError(
            f"Файлы с расширением {extension} загружать нельзя: "
            "это может быть исполняемая программа."
        )
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise UploadError(f"Такое расширение не поддерживается. Можно: {allowed}")

    # --- Проверка 2: размер ---
    limit = (max_bytes or config.MAX_UPLOAD_SIZE_MB * 1024 * 1024)
    storage.seek(0, os.SEEK_END)
    size = storage.tell()
    storage.seek(0)
    if size == 0:
        raise UploadError("Файл пустой.")
    if size > limit:
        raise UploadError(
            f"Файл слишком большой: {size / 1024 / 1024:.1f} МБ. "
            f"Максимум — {limit / 1024 / 1024:.0f} МБ."
        )

    # --- Проверка 3: реальное содержимое ---
    data = storage.read()
    real_type = detect_image_type(data)
    if real_type is None:
        raise UploadError(
            "Этот файл не похож на изображение. "
            "Проверьте, что вы выбрали настоящую картинку (JPG, PNG, WEBP, GIF или SVG)."
        )

    # Расширение и содержимое должны совпадать (кроме jpg/jpeg — это одно и то же)
    expected = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml",
    }[extension]
    if expected != real_type:
        raise UploadError(
            "Содержимое файла не совпадает с его расширением. "
            "Похоже, файл переименован — загрузите исходное изображение."
        )

    return data, real_type


def save_upload(storage, folder, prefix=""):
    """
    Проверяет файл и сохраняет его в папку.
    Возвращает путь ОТНОСИТЕЛЬНО папки static/ — именно в таком виде
    пути хранятся в базе (например: images/uploads/shema-1a2b3c4d.jpg).

    folder — подпапка внутри static/images, например "uploads".
    """
    data, _mime = validate_image(storage)

    directory = os.path.join(config.STATIC_DIR, "images", folder)
    os.makedirs(directory, exist_ok=True)

    name = safe_upload_name(storage.filename, prefix=prefix)
    full_path = os.path.join(directory, name)

    # Дополнительная защита: имя не должно выйти за пределы папки
    if not os.path.abspath(full_path).startswith(os.path.abspath(directory)):
        raise UploadError("Недопустимое имя файла.")

    with open(full_path, "wb") as file:
        file.write(data)

    return f"images/{folder}/{name}"


def delete_upload(relative_path):
    """
    Удаляет файл изображения, если он был загружен через админ-панель.
    Файлы из прежних папок (images/patterns и т. п.) не трогаем —
    их мог положить сам автор вручную.
    """
    if not relative_path or not isinstance(relative_path, str):
        return False
    if not relative_path.startswith("images/uploads/"):
        return False
    if ".." in relative_path or "\\" in relative_path:
        return False

    full_path = os.path.join(config.STATIC_DIR, relative_path.replace("/", os.sep))
    if os.path.isfile(full_path):
        try:
            os.remove(full_path)
            return True
        except OSError:
            return False
    return False


# --------------------------------------------------------------------------
# 5. АККАУНТЫ ПОКУПАТЕЛЕЙ: ПАРОЛИ И ТОКЕНЫ
# --------------------------------------------------------------------------
# Эти функции дополняют уже описанные выше: хеширование пароля и CSRF
# одинаковы для администратора и покупателя, а вот работа с токенами
# подтверждения почты и сброса пароля нужна только аккаунтам.

# Сколько символов допускаем в отзывах и рассказах (см. config)
def clean_text(value, max_length):
    """
    Готовит пользовательский текст к сохранению:
    убирает управляющие символы, лишние пробелы и обрезает по длине.

    HTML-теги мы НЕ вырезаем «наугад»: их безопасно показывает сама
    система шаблонов Jinja2 (экранирование по умолчанию). Здесь важно
    убрать невидимый мусор и не дать залить гигантский текст.
    """
    if not value:
        return ""
    # Убираем управляющие символы, кроме перевода строки и табуляции
    text = "".join(
        ch for ch in str(value)
        if ch in ("\n", "\t") or ord(ch) >= 32
    )
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Не больше двух пустых строк подряд
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    text = text.strip()
    if max_length and len(text) > max_length:
        text = text[:max_length].rstrip()
    return text


def validate_email(email):
    """Простая и надёжная проверка адреса почты. Возвращает текст ошибки или None."""
    email = (email or "").strip()
    if not email:
        return "Введите адрес электронной почты."
    if len(email) > 254:
        return "Адрес слишком длинный."
    # Одна «собачка», точка в домене, без пробелов
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return "Проверьте адрес: он должен быть вида imya@example.ru"
    return None


def validate_display_name(name):
    """Публичное имя: не пустое, без лишних символов, ограниченной длины."""
    name = clean_text(name, config.DISPLAY_NAME_MAX_LENGTH + 10)
    if not name:
        return None, "Укажите, как показать ваше имя."
    if len(name) > config.DISPLAY_NAME_MAX_LENGTH:
        return None, f"Имя длиннее {config.DISPLAY_NAME_MAX_LENGTH} символов."
    return name, None


def make_token_pair():
    """
    Создаёт пару «открытый токен — его хеш».

    Покупателю уходит открытый токен (в ссылке). В базе хранится только
    хеш: если база попадёт в чужие руки, восстановить ссылку нельзя.
    """
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw_token):
    """Хеш токена (SHA-256). Для сравнения используется hmac.compare_digest."""
    return hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()


def tokens_equal_hash(stored_hash, raw_token):
    """Безопасно сравнивает сохранённый хеш с хешем предъявленного токена."""
    if not stored_hash or not raw_token:
        return False
    return hmac.compare_digest(stored_hash, hash_token(raw_token))


def content_fingerprint(text):
    """
    «Отпечаток» текста для защиты от массовой отправки одинаковых отзывов.
    Регистр, пробелы и знаки препинания не учитываются.
    """
    normalized = re.sub(r"[^\wа-яё]+", "", (text or "").lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# 6. БЕЗОПАСНОСТЬ ФОТОГРАФИЙ ПОЛЬЗОВАТЕЛЕЙ
# --------------------------------------------------------------------------
# Требования: только JPEG/PNG/WebP, проверка реального формата, ограничение
# размера, пересохранение в безопасном виде, удаление EXIF (в том числе
# геолокации), случайные имена. SVG и GIF здесь не принимаем.

_PROJECT_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_PROJECT_FORMAT_MAP = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


def validate_project_image(storage, max_bytes=None):
    """
    Проверяет фотографию отшива или отзыва.

    Возвращает (данные_файла, реальный_mime). При проблеме — UploadError
    с понятным русским текстом.
    """
    if storage is None or not getattr(storage, "filename", ""):
        raise UploadError("Файл не выбран.")

    filename = _clean_filename(storage.filename)
    extension = os.path.splitext(filename)[1].lower()

    if extension in FORBIDDEN_EXTENSIONS:
        raise UploadError(
            "Такой файл загрузить нельзя: это может быть программа."
        )
    if extension not in _PROJECT_ALLOWED_EXT:
        raise UploadError("Фотография должна быть в формате JPG, PNG или WEBP.")

    limit = (max_bytes or config.MAX_PROJECT_IMAGE_MB * 1024 * 1024)
    storage.seek(0, os.SEEK_END)
    size = storage.tell()
    storage.seek(0)
    if size == 0:
        raise UploadError("Файл пустой.")
    if size > limit:
        raise UploadError(
            f"Фотография слишком большая: {size / 1024 / 1024:.1f} МБ. "
            f"Максимум — {limit / 1024 / 1024:.0f} МБ."
        )

    data = storage.read()
    real_type = detect_image_type(data)
    if real_type not in _PROJECT_FORMAT_MAP:
        raise UploadError(
            "Это не похоже на фотографию. Подходят только JPG, PNG и WEBP."
        )

    expected = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
    }[extension]
    if expected != real_type:
        raise UploadError(
            "Содержимое файла не совпадает с расширением. "
            "Загрузите исходное фото без переименования."
        )

    # Проверяем, что картинка действительно открывается (защита от «битых»
    # и специально испорченных файлов).
    try:
        from PIL import Image
        import io as _io
        with Image.open(_io.BytesIO(data)) as probe:
            probe.verify()
    except Exception:
        raise UploadError("Не удалось прочитать изображение. Попробуйте другой файл.")

    return data, real_type


def safe_project_image(data, mime_type, max_side=None):
    """
    Пересохраняет фотографию в безопасном виде:
      * убирает EXIF (в том числе координаты съёмки);
      * уменьшает слишком большие снимки, сохраняя пропорции;
      * приводит цветовой режим к RGB.

    Возвращает (bytes_нового_файла, расширение) — например (b"...", ".jpg").
    """
    from PIL import Image
    import io as _io

    max_side = max_side or config.PUBLIC_IMAGE_MAX_SIDE
    fmt = _PROJECT_FORMAT_MAP.get(mime_type, "JPEG")

    with Image.open(_io.BytesIO(data)) as image:
        # Поворачиваем по EXIF ДО удаления метаданных — иначе фото
        # с телефона может оказаться «лёжа на боку».
        try:
            from PIL import ImageOps
            image = ImageOps.exif_transpose(image)
        except Exception:
            pass

        if fmt == "JPEG" and image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        elif fmt == "PNG" and image.mode == "P":
            image = image.convert("RGBA")

        # Уменьшаем, только если фото больше предела (пропорции сохраняем)
        if max(image.width, image.height) > max_side:
            ratio = max_side / float(max(image.width, image.height))
            new_size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
            image = image.resize(new_size, Image.LANCZOS)

        output = _io.BytesIO()
        if fmt == "JPEG":
            # В новом файле EXIF не сохраняем вовсе
            image.save(output, format="JPEG", quality=86, optimize=True)
            extension = ".jpg"
        elif fmt == "PNG":
            image.save(output, format="PNG", optimize=True)
            extension = ".png"
        else:
            image.save(output, format="WEBP", quality=86, method=4)
            extension = ".webp"

    return output.getvalue(), extension


def save_project_photo(storage, prefix="proekt"):
    """
    Проверяет фотографию, пересохраняет в безопасном виде и кладёт её
    в папку оригиналов (её содержимое НЕ публично).

    Возвращает имя файла (только имя, без пути) — оно хранится в базе.
    """
    data, mime_type = validate_project_image(storage)
    safe_bytes, extension = safe_project_image(data, mime_type)

    os.makedirs(config.PROJECT_UPLOAD_DIR, exist_ok=True)

    prefix = re.sub(r"[^a-z0-9\-]+", "-", (prefix or "").lower()).strip("-")
    name = f"{prefix}-{secrets.token_hex(8)}{extension}"
    full_path = os.path.join(config.PROJECT_UPLOAD_DIR, name)

    # Файл не должен выйти за пределы папки оригиналов
    if not os.path.abspath(full_path).startswith(os.path.abspath(config.PROJECT_UPLOAD_DIR)):
        raise UploadError("Недопустимое имя файла.")

    with open(full_path, "wb") as file:
        file.write(safe_bytes)
    return name


def publish_project_photo(stored_name):
    """
    Делает оптимизированную копию для публичного показа.

    Оригинал остаётся в защищённой папке; на сайте показывается только
    эта копия. Возвращает путь относительно static/ (для базы).
    """
    source = os.path.join(config.PROJECT_UPLOAD_DIR, os.path.basename(stored_name))
    if not os.path.isfile(source):
        return ""

    os.makedirs(config.PUBLIC_UPLOAD_DIR, exist_ok=True)

    with open(source, "rb") as file:
        data = file.read()

    mime_type = detect_image_type(data) or "image/jpeg"
    safe_bytes, extension = safe_project_image(
        data, mime_type, max_side=config.PUBLIC_IMAGE_MAX_SIDE
    )

    public_name = f"{secrets.token_hex(8)}{extension}"
    full_path = os.path.join(config.PUBLIC_UPLOAD_DIR, public_name)
    with open(full_path, "wb") as file:
        file.write(safe_bytes)

    return f"images/projects/{public_name}"


def delete_protected_file(stored_name):
    """Удаляет оригинал фотографии из защищённой папки."""
    if not stored_name:
        return False
    name = os.path.basename(stored_name)
    full_path = os.path.join(config.PROJECT_UPLOAD_DIR, name)
    if os.path.isfile(full_path):
        try:
            os.remove(full_path)
            return True
        except OSError:
            return False
    return False


def delete_public_project_image(relative_path):
    """Удаляет опубликованную копию фотографии (только из images/projects/)."""
    if not relative_path or not isinstance(relative_path, str):
        return False
    if not relative_path.startswith("images/projects/") or ".." in relative_path:
        return False
    full_path = os.path.join(config.STATIC_DIR, relative_path.replace("/", os.sep))
    if os.path.isfile(full_path):
        try:
            os.remove(full_path)
            return True
        except OSError:
            return False
    return False


def safe_protected_name(filename):
    """
    Готовит безопасное имя для цифрового файла схемы (PDF и т. п.),
    который кладёт администратор. Разширение сохраняем.
    """
    filename = _clean_filename(filename).lower()
    name, extension = os.path.splitext(filename)
    name = re.sub(r"[^a-z0-9\-]+", "-", name).strip("-") or "shema"
    extension = re.sub(r"[^a-z0-9.]", "", extension)
    return f"{name[:60]}-{secrets.token_hex(6)}{extension}"
