# -*- coding: utf-8 -*-
"""
users.py — личные кабинеты покупателей.

Здесь живут:

    /register                 — регистрация
    /login                    — вход
    /logout                   — выход
    /confirm-email/<token>    — подтверждение почты по ссылке
    /reset                    — запрос сброса пароля
    /reset/<token>            — установка нового пароля

    /account                  — личный кабинет (сводка)
    /account/library          — моя библиотека схем
    /account/download/<id>    — защищённое скачивание файла схемы
    /account/orders           — история заказов
    /account/projects         — мои отшивы (+ форма «Поделиться отшивом»)
    /account/reviews          — мои отзывы (+ форма «Написать отзыв»)
    /account/reviews/write    — страница создания отзыва
    /account/settings         — настройки профиля

Важное правило: пароли хранятся только в виде хеша, а письма на почту
НЕ отправляются, пока не подключён почтовый сервис. Вместо этого работает
честный локальный режим разработки (см. config.EMAIL_DEV_MODE).
"""

import os
from datetime import datetime, timedelta

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template,
    request, send_file, session, url_for,
)
from flask_login import (
    LoginManager, UserMixin, current_user, login_required, login_user, logout_user,
)

import config
import database
import security
from security import UploadError

users = Blueprint("users", __name__)

# --------------------------------------------------------------------------
# Flask-Login: кто сейчас вошёл в аккаунт покупателя
# --------------------------------------------------------------------------
login_manager = LoginManager()
login_manager.login_view = "users.login"
login_manager.login_message = "Войдите в аккаунт, чтобы открыть личный кабинет."
login_manager.login_message_category = "warning"


class Customer(UserMixin):
    """
    Обёртка над записью покупателя, которую понимает Flask-Login.

    Сам пароль сюда не попадает: в объекте только публичные данные.
    """

    def __init__(self, data):
        self.id = data["id"]
        self.name = data.get("name", "")
        self.nickname = data.get("nickname", "")
        self.email = data.get("email", "")
        self.email_confirmed = bool(data.get("email_confirmed"))
        self.is_blocked = bool(data.get("is_blocked"))
        self.display_name_mode = data.get("display_name_mode", "first")
        self.display_name_custom = data.get("display_name_custom", "")
        self.data = data

    @property
    def is_active(self):
        # Заблокированный аккаунт не может войти и работать на сайте
        return not self.is_blocked

    @property
    def display_name(self):
        """Публичное имя покупателя (без email — он всегда остаётся тайной)."""
        return database.public_display_name(self.data)


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login вызывает эту функцию, чтобы «вспомнить» вошедшего."""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None
    data = database.get_user(user_id)
    if data is None or data["deleted_at"]:
        return None
    return Customer(data)


# --------------------------------------------------------------------------
# CSRF для форм публичного сайта
# --------------------------------------------------------------------------
# Используется та же схема, что и в админ-панели: токен лежит в сессии,
# и каждая форма отправляет его скрытым полем.
def get_csrf_token():
    """Возвращает токен для формы, создавая его при необходимости."""
    if "csrf_token" not in session:
        session["csrf_token"] = security.make_csrf_token()
    return session["csrf_token"]


def check_csrf():
    """Проверяет токен формы. Неверный токен — отказ (403)."""
    expected = session.get("csrf_token")
    received = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not security.tokens_match(expected, received):
        abort(403, description="Недействительный токен формы. Обновите страницу.")


# --------------------------------------------------------------------------
# Письма: честный локальный режим (без имитации отправки)
# --------------------------------------------------------------------------
def _dev_link_token(purpose):
    """
    Создаёт токен для ссылки и возвращает (открытый_токен, ссылка).

    В режиме разработки ссылка показывается прямо на странице. Когда
    появится почтовый сервис, функция здесь же отправит письмо.
    """
    lifetime_hours = (
        config.RESET_TOKEN_LIFETIME_HOURS if purpose == "reset_password"
        else config.EMAIL_TOKEN_LIFETIME_HOURS
    )
    raw_token, token_hash = security.make_token_pair()
    expires = (datetime.now() + timedelta(hours=lifetime_hours)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    return raw_token, token_hash, expires, lifetime_hours


def _email_confirmation_link(raw_token):
    """Полная ссылка подтверждения почты (без домена — его добавит шаблон)."""
    return url_for("users.confirm_email", token=raw_token, _external=True)


def _reset_link(raw_token):
    """Полная ссылка сброса пароля."""
    return url_for("users.reset_password", token=raw_token, _external=True)


def _send_email_note(action, link):
    """
    Возвращает подсказку о письме для страницы.

    Пока EMAIL_DEV_MODE включён, письмо НЕ отправляется: сайт честно
    говорит об этом и показывает ссылку, чтобы всё можно было проверить.
    """
    if config.EMAIL_DEV_MODE:
        return {
            "dev_mode": True,
            "link": link,
            "text": (
                "Почтовый сервис пока не подключён, письмо не отправлено. "
                "Ниже — ссылка для проверки. Она действует ограниченное время."
            ),
        }
    return {
        "dev_mode": False,
        "link": "",
        "text": f"Мы отправили письмо ({action}). Проверьте почту.",
    }


# ==========================================================================
# РЕГИСТРАЦИЯ, ВХОД, ВЫХОД
# ==========================================================================

@users.route("/register", methods=["GET", "POST"])
def register():
    """Регистрация покупателя."""
    if current_user.is_authenticated:
        return redirect(url_for("users.account"))

    errors = {}
    values = {"name": "", "nickname": "", "email": ""}
    confirm_link = None

    if request.method == "POST":
        check_csrf()
        values = {
            "name": (request.form.get("name") or "").strip(),
            "nickname": (request.form.get("nickname") or "").strip(),
            "email": (request.form.get("email") or "").strip(),
        }
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""

        # --- Имя ---
        if not values["name"]:
            errors["name"] = "Введите имя."
        elif len(values["name"]) > 80:
            errors["name"] = "Имя слишком длинное."

        # --- Никнейм (необязательный) ---
        if values["nickname"] and len(values["nickname"]) > 40:
            errors["nickname"] = "Никнейм длиннее 40 символов."

        # --- Почта ---
        email_error = security.validate_email(values["email"])
        if email_error:
            errors["email"] = email_error
        elif database.get_user_by_email(values["email"]):
            errors["email"] = "Такая почта уже зарегистрирована. Войдите в аккаунт."

        # --- Пароль ---
        problems = security.password_problems(password)
        if problems:
            errors["password"] = "Пароль не подходит: " + ", ".join(problems) + "."
        elif password != password2:
            errors["password2"] = "Пароли не совпадают."

        if not errors:
            user_id = database.create_user(
                name=values["name"],
                email=values["email"],
                password_hash=security.hash_password(password),
                nickname=values["nickname"],
                email_confirmed=False,
            )
            if user_id is None:
                errors["email"] = "Такая почта уже зарегистрирована."
            else:
                # Готовим ссылку подтверждения почты
                raw_token, token_hash, expires, hours = _dev_link_token("confirm_email")
                database.create_user_token(
                    user_id, token_hash, "confirm_email", expires
                )
                link = _email_confirmation_link(raw_token)
                note = _send_email_note("подтверждение почты", link)
                confirm_link = note

                flash(
                    "Аккаунт создан. Подтвердите почту, чтобы оставлять отзывы "
                    "и делиться отшивами.",
                    "success",
                )
                return render_template(
                    "auth/confirm_sent.html",
                    email=values["email"],
                    note=note,
                    hours=hours,
                )

    return render_template(
        "auth/register.html", errors=errors, values=values
    )


@users.route("/confirm-email/<token>")
def confirm_email(token):
    """Подтверждение почты по ссылке из письма."""
    token_hash = security.hash_token(token)
    found = database.find_user_token(token_hash, "confirm_email")
    if found is None:
        return render_template("auth/token_invalid.html"), 400

    database.confirm_user_email(found["user_id"])
    database.use_user_token(found["id"])
    flash("Почта подтверждена. Спасибо! Теперь доступны отзывы и отшивы.", "success")

    # Если человек уже вошёл — обновим его данные, чтобы подтверждение
    # сразу вступило в силу в текущей сессии
    if current_user.is_authenticated and current_user.id == found["user_id"]:
        login_user(load_user(found["user_id"]))

    return redirect(url_for("users.login"))


@users.route("/login", methods=["GET", "POST"])
def login():
    """Вход в аккаунт покупателя."""
    if current_user.is_authenticated:
        return redirect(url_for("users.account"))

    errors = {}
    email = ""

    if request.method == "POST":
        check_csrf()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        ip = request.remote_addr or ""

        failed = database.recent_failed_user_attempts(
            ip, config.LOGIN_ATTEMPT_WINDOW_MINUTES
        )
        if security.login_is_blocked(failed):
            errors["general"] = (
                f"Слишком много неудачных попыток входа. Подождите "
                f"{config.LOGIN_ATTEMPT_WINDOW_MINUTES} минут."
            )
        elif not email or not password:
            errors["general"] = "Введите почту и пароль."
        else:
            # Проверяем и хеш пароля, и блокировку аккаунта.
            user = database.get_user_by_email_with_hash(email)
            if user and security.verify_password(user["password_hash"], password):
                if user["is_blocked"]:
                    errors["general"] = (
                        "Аккаунт заблокирован. Напишите нам, если это ошибка."
                    )
                    database.add_user_login_attempt(email, ip, success=False)
                else:
                    database.add_user_login_attempt(email, ip, success=True)
                    database.clear_user_login_attempts(ip)
                    database.touch_user_login(user["id"])

                    # Очищаем сессию и выдаём новый токен CSRF — защита
                    # от «зафиксированной» сессии
                    session.clear()
                    login_user(Customer(user), remember=True)
                    session["csrf_token"] = security.make_csrf_token()

                    flash(f"Здравствуйте, {user['name'] or 'друг'}!", "success")
                    next_url = request.args.get("next")
                    if next_url and next_url.startswith("/account"):
                        return redirect(next_url)
                    return redirect(url_for("users.account"))
            else:
                database.add_user_login_attempt(email, ip, success=False)
                # Одинаковый текст для неверной почты и пароля
                errors["general"] = "Неверная почта или пароль."

    return render_template("auth/login.html", errors=errors, email=email)


@users.route("/logout", methods=["POST"])
@login_required
def logout():
    """Выход из аккаунта."""
    check_csrf()
    # Порядок важен: сначала очищаем сессию, потом выходим.
    # logout_user() ставит служебную отметку, по которой Flask-Login
    # удаляет cookie «запомнить меня». Если очистить сессию ПОСЛЕ этого,
    # отметка пропадёт и вход «запомнится» снова.
    session.clear()
    logout_user()
    flash("Вы вышли из аккаунта.", "success")
    return redirect(url_for("index"))


# ==========================================================================
# ВОССТАНОВЛЕНИЕ ПАРОЛЯ
# ==========================================================================

@users.route("/reset", methods=["GET", "POST"])
def reset_request():
    """Запрос сброса пароля: покупатель вводит почту."""
    note = None
    if request.method == "POST":
        check_csrf()
        email = (request.form.get("email") or "").strip()
        user = database.get_user_by_email(email)
        # Отвечаем одинаково независимо от того, есть такой аккаунт или нет —
        # так нельзя «выяснить» чужие адреса перебором.
        if user:
            raw_token, token_hash, expires, hours = _dev_link_token("reset_password")
            database.invalidate_user_tokens(user["id"], "reset_password")
            database.create_user_token(user["id"], token_hash, "reset_password", expires)
            note = _send_email_note("сброс пароля", _reset_link(raw_token))
        else:
            note = {
                "dev_mode": config.EMAIL_DEV_MODE,
                "link": "",
                "text": "Если такая почта зарегистрирована, письмо со ссылкой отправлено.",
            }
    return render_template("auth/reset_request.html", note=note)


@users.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Установка нового пароля по ссылке."""
    token_hash = security.hash_token(token)
    found = database.find_user_token(token_hash, "reset_password")
    if found is None:
        return render_template("auth/token_invalid.html"), 400

    errors = {}
    if request.method == "POST":
        check_csrf()
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""
        problems = security.password_problems(password)
        if problems:
            errors["password"] = "Пароль не подходит: " + ", ".join(problems) + "."
        elif password != password2:
            errors["password2"] = "Пароли не совпадают."
        else:
            database.set_user_password(found["user_id"], security.hash_password(password))
            database.use_user_token(found["id"])
            database.invalidate_user_tokens(found["user_id"], "reset_password")
            flash("Пароль изменён. Войдите с новым паролем.", "success")
            return redirect(url_for("users.login"))

    return render_template("auth/reset_password.html", errors=errors, token=token)


# ==========================================================================
# ЛИЧНЫЙ КАБИНЕТ
# ==========================================================================

@users.route("/account")
@login_required
def account():
    """Сводка: библиотека, отшивы, отзывы, заказы."""
    library = database.list_user_library(current_user.id)
    projects = database.list_projects(user_id=current_user.id)
    reviews = database.list_user_reviews(current_user.id)
    orders = database.list_user_orders(current_user.id)
    return render_template(
        "account/dashboard.html",
        library=library,
        projects=projects,
        reviews=reviews,
        orders=orders,
    )


@users.route("/account/library")
@login_required
def library():
    """Мои схемы: только те, на которые выдано право скачивания."""
    return render_template(
        "account/library.html",
        library=database.list_user_library(current_user.id),
    )


@users.route("/account/download/<int:file_id>")
@login_required
def download(file_id):
    """
    Защищённое скачивание цифрового файла схемы.

    Проверки по порядку:
      1) покупатель вошёл (это делает @login_required);
      2) файл существует и включён;
      3) у покупателя есть действующее право на ЭТУ схему;
      4) файл действительно лежит в защищённой папке.

    Изменение id в адресе не поможет: право проверяется по пользователю
    из сессии, а не по ссылке.
    """
    pattern_file = database.get_pattern_file(file_id)
    if pattern_file is None or not pattern_file["is_active"]:
        abort(404)

    if not database.user_has_entitlement(current_user.id, pattern_file["pattern_id"]):
        abort(403, description="К этой схеме у вас нет права скачивания.")

    stored_name = os.path.basename(pattern_file["stored_name"])
    full_path = os.path.join(config.PROTECTED_DIR, stored_name)
    # Дополнительная защита от выхода за пределы папки
    if not os.path.abspath(full_path).startswith(os.path.abspath(config.PROTECTED_DIR)):
        abort(404)
    if not os.path.isfile(full_path):
        abort(404, description="Файл пока не загружен. Напишите нам.")

    pattern = database.get_pattern(pattern_file["pattern_id"])
    title = pattern["title"] if pattern else "shema"
    download_name = f"{pattern_file['format']}-{security.safe_protected_name(title)}"
    if not os.path.splitext(download_name)[1]:
        download_name += os.path.splitext(stored_name)[1]

    return send_file(
        full_path,
        as_attachment=True,
        download_name=download_name,
        max_age=0,
    )


@users.route("/account/orders")
@login_required
def orders():
    """Мои заказы. Покупатель видит только свои записи."""
    return render_template(
        "account/orders.html",
        orders=database.list_user_orders(current_user.id),
    )


# ==========================================================================
# ОТШИВЫ (ГОТОВЫЕ РАБОТЫ)
# ==========================================================================

@users.route("/account/projects", methods=["GET", "POST"])
@login_required
def projects():
    """Мои отшивы и форма «Поделиться отшивом»."""
    errors = {}

    if request.method == "POST":
        check_csrf()

        # Отзыв согласия на публикацию существующей работы
        if request.form.get("action") == "withdraw":
            project_id = request.form.get("project_id", type=int)
            project = database.get_project(project_id)
            if project and project["user_id"] == current_user.id:
                database.set_project_consent(project_id, False)
                database.log_moderation(
                    "project", project_id, "withdraw",
                    "Покупатель отозвал согласие", current_user.display_name,
                )
                flash(
                    "Согласие отозвано. Работа снята с публичного показа.",
                    "success",
                )
            return redirect(url_for("users.projects"))

        # Загрузка нового отшива
        return _submit_project(errors)

    patterns = database.list_published_patterns()
    return render_template(
        "account/projects.html",
        projects=database.list_projects(user_id=current_user.id),
        patterns=patterns,
        errors=errors,
        values={},
        max_images=config.MAX_PROJECT_IMAGES,
    )


def _submit_project(errors):
    """Обрабатывает форму «Поделиться отшивом»."""
    pattern_id = request.form.get("pattern_id", type=int)
    story = security.clean_text(
        request.form.get("story"), config.PROJECT_STORY_MAX_LENGTH
    )
    display_name = (request.form.get("display_name") or "").strip()
    owns_photos = request.form.get("owns_photos") == "1"
    publish_consent = request.form.get("publish_consent") == "1"

    # --- Проверка частоты отправки (защита от спама) ---
    recent = database.list_projects(user_id=current_user.id, limit=1)
    if recent:
        last_time = recent[0]["created_at"]
        try:
            last = datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")
            if datetime.now() - last < timedelta(minutes=config.PROJECT_COOLDOWN_MINUTES):
                flash(
                    "Слишком часто. Подождите немного перед следующей отправкой.",
                    "error",
                )
                return redirect(url_for("users.projects"))
        except ValueError:
            pass

    # --- Схема ---
    pattern = database.get_pattern(pattern_id) if pattern_id else None
    if pattern is None:
        errors["pattern_id"] = "Выберите схему из списка."

    # --- Текст ---
    if not story:
        errors["story"] = "Расскажите немного о работе."
    elif len(story) < 10:
        errors["story"] = "Рассказ слишком короткий — добавьте пару слов."

    # --- Публичное имя ---
    name, name_error = security.validate_display_name(display_name)
    if name_error:
        errors["display_name"] = name_error

    # --- Согласия ---
    if not owns_photos:
        errors["owns_photos"] = "Подтвердите, что фото ваши."
    if not publish_consent:
        errors["publish_consent"] = "Нужно согласие на публикацию."

    # --- Фотографии ---
    files = [f for f in request.files.getlist("photos") if f and f.filename]
    if not files:
        errors["photos"] = "Добавьте хотя бы одну фотографию."
    elif len(files) > config.MAX_PROJECT_IMAGES:
        errors["photos"] = f"Не больше {config.MAX_PROJECT_IMAGES} фотографий."

    if errors:
        flash("Проверьте отмеченные поля.", "error")
        return render_template(
            "account/projects.html",
            projects=database.list_projects(user_id=current_user.id),
            patterns=database.list_published_patterns(),
            errors=errors,
            values={
                "pattern_id": pattern_id,
                "story": story,
                "display_name": display_name,
            },
            max_images=config.MAX_PROJECT_IMAGES,
        )

    # --- Сохраняем фотографии в защищённую папку (оригиналы не публичны) ---
    stored_names = []
    try:
        for upload in files:
            stored_names.append(security.save_project_photo(upload, prefix="proekt"))
    except UploadError as error:
        for name in stored_names:
            security.delete_protected_file(name)
        errors["photos"] = str(error)
        flash("Проблема с фотографией: " + str(error), "error")
        return render_template(
            "account/projects.html",
            projects=database.list_projects(user_id=current_user.id),
            patterns=database.list_published_patterns(),
            errors=errors,
            values={"pattern_id": pattern_id, "story": story, "display_name": display_name},
            max_images=config.MAX_PROJECT_IMAGES,
        )

    project_id = database.create_finished_project(
        user_id=current_user.id,
        pattern_id=pattern_id,
        story=story,
        display_name=name,
        owns_photos=owns_photos,
        publish_consent=publish_consent,
    )
    for position, stored in enumerate(stored_names, start=1):
        database.add_project_image(project_id, stored, position)

    flash(
        "Спасибо! Отшив отправлен на проверку. Статус: «Ожидает проверки».",
        "success",
    )
    return redirect(url_for("users.projects"))


# ==========================================================================
# ОТЗЫВЫ
# ==========================================================================

@users.route("/account/reviews")
@login_required
def reviews():
    """Мои отзывы и их статусы."""
    return render_template(
        "account/reviews.html",
        reviews=database.list_user_reviews(current_user.id),
    )


@users.route("/account/reviews/write", methods=["GET", "POST"])
@login_required
def write_review():
    """Форма «Написать отзыв»."""
    errors = {}
    patterns = database.list_published_patterns()
    values = {"category": "pattern", "rating": "5", "text": "", "pattern_id": ""}

    if request.method == "POST":
        check_csrf()

        # Отзывы может оставлять только покупатель с подтверждённой почтой
        if not current_user.email_confirmed:
            flash(
                "Чтобы оставить отзыв, подтвердите почту. Проверьте письмо "
                "или запросите новое.",
                "warning",
            )
            return redirect(url_for("users.account"))

        category = request.form.get("category") or "pattern"
        rating = request.form.get("rating", type=int) or 0
        text = security.clean_text(request.form.get("text"), config.REVIEW_MAX_LENGTH)
        pattern_id = request.form.get("pattern_id", type=int)
        display_name = (request.form.get("display_name") or "").strip()

        if category not in dict(config.REVIEW_CATEGORIES):
            errors["category"] = "Выберите категорию отзыва."
        if rating < 1 or rating > 5:
            errors["rating"] = "Поставьте оценку от 1 до 5."
        if not text or len(text) < 10:
            errors["text"] = "Напишите отзыв (хотя бы пару предложений)."
        if category == "pattern" and not pattern_id:
            errors["pattern_id"] = "Выберите схему, о которой отзыв."

        name, name_error = security.validate_display_name(display_name)
        if name_error:
            errors["display_name"] = name_error

        # --- Защита от одинаковых текстов ---
        fingerprint = security.content_fingerprint(text)
        identical = database.count_identical_reviews(current_user.id, fingerprint)
        if not errors and identical >= config.REVIEW_MAX_IDENTICAL:
            errors["text"] = "Такой отзыв вы уже отправляли."

        # --- Ограничение частоты ---
        recent = database.list_reviews(user_id=current_user.id, limit=1)
        if not errors and recent:
            try:
                last = datetime.strptime(recent[0]["created_at"], "%Y-%m-%d %H:%M:%S")
                if datetime.now() - last < timedelta(minutes=config.REVIEW_COOLDOWN_MINUTES):
                    errors["text"] = "Подождите немного перед следующим отзывом."
            except ValueError:
                pass

        # --- Необязательное фото ---
        photo_path = ""
        photo = request.files.get("photo")
        if photo and photo.filename:
            try:
                stored = security.save_project_photo(photo, prefix="otzyv")
                # Для отзыва публикуем оптимизированную копию сразу:
                # фото в отзыве показывается маленьким и не является
                # «оригиналом высокого разрешения»
                photo_path = security.publish_project_photo(stored)
                security.delete_protected_file(stored)
            except UploadError as error:
                errors["photo"] = str(error)

        if not errors:
            # Отметка «Покупка подтверждена» — только для покупок на сайте
            verified = database.has_verified_purchase(current_user.id, pattern_id)
            database.create_review(
                user_id=current_user.id,
                text=text,
                rating=rating,
                display_name=name,
                category=category,
                pattern_id=pattern_id if category == "pattern" else None,
                photo_path=photo_path,
                verified_purchase=verified,
                content_hash=fingerprint,
            )
            flash(
                "Спасибо за отзыв! Он появится после проверки — "
                "статус виден в разделе «Мои отзывы».",
                "success",
            )
            return redirect(url_for("users.reviews"))

        values = {
            "category": category,
            "rating": str(rating or ""),
            "text": text,
            "pattern_id": str(pattern_id or ""),
            "display_name": display_name,
        }
        flash("Проверьте отмеченные поля.", "error")

    # Значение схемы можно передать в адресе: ?pattern=slug
    preset_slug = request.args.get("pattern")
    if preset_slug and not values.get("pattern_id"):
        pattern = database.get_pattern_by_slug(preset_slug)
        if pattern:
            values["pattern_id"] = str(pattern["id"])

    # Подсказка: покупал ли пользователь эту схему на сайте
    return render_template(
        "account/write_review.html",
        errors=errors,
        patterns=patterns,
        values=values,
        categories=config.REVIEW_CATEGORIES,
        display_name=current_user.display_name,
    )


# ==========================================================================
# НАСТРОЙКИ ПРОФИЛЯ
# ==========================================================================

@users.route("/account/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Настройки профиля: имя, никнейм, публичное имя, пароль."""
    errors = {}
    note = None

    if request.method == "POST":
        check_csrf()
        action = request.form.get("action") or "profile"

        if action == "profile":
            name = (request.form.get("name") or "").strip()
            nickname = (request.form.get("nickname") or "").strip()
            mode = request.form.get("display_name_mode") or "first"
            custom = (request.form.get("display_name_custom") or "").strip()

            if not name:
                errors["name"] = "Введите имя."
            if nickname and len(nickname) > 40:
                errors["nickname"] = "Никнейм длиннее 40 символов."
            if mode not in ("full", "nickname", "first", "custom"):
                errors["display_name_mode"] = "Выберите способ показа имени."
            if mode == "custom" and not custom:
                errors["display_name_custom"] = "Введите своё отображаемое имя."
            if custom and len(custom) > config.DISPLAY_NAME_MAX_LENGTH:
                errors["display_name_custom"] = (
                    f"Не длиннее {config.DISPLAY_NAME_MAX_LENGTH} символов."
                )

            if not errors:
                database.update_user(current_user.id, {
                    "name": name,
                    "nickname": nickname,
                    "display_name_mode": mode if mode != "custom" else "first",
                    "display_name_custom": custom if mode == "custom" else "",
                })
                login_user(load_user(current_user.id))
                flash("Настройки профиля сохранены.", "success")
                return redirect(url_for("users.settings"))

        elif action == "password":
            current_password = request.form.get("current_password") or ""
            new_password = request.form.get("new_password") or ""
            new_password2 = request.form.get("new_password2") or ""

            stored_hash = database.get_user_password_hash(current_user.id)
            if not security.verify_password(stored_hash, current_password):
                errors["current_password"] = "Текущий пароль указан неверно."
            problems = security.password_problems(new_password)
            if problems:
                errors["new_password"] = "Пароль не подходит: " + ", ".join(problems) + "."
            elif new_password != new_password2:
                errors["new_password2"] = "Пароли не совпадают."

            if not errors:
                database.set_user_password(
                    current_user.id, security.hash_password(new_password)
                )
                flash("Пароль изменён.", "success")
                return redirect(url_for("users.settings"))

        elif action == "resend_confirmation":
            if current_user.email_confirmed:
                flash("Почта уже подтверждена.", "success")
                return redirect(url_for("users.settings"))
            raw_token, token_hash, expires, hours = _dev_link_token("confirm_email")
            database.invalidate_user_tokens(current_user.id, "confirm_email")
            database.create_user_token(current_user.id, token_hash, "confirm_email", expires)
            note = _send_email_note(
                "подтверждение почты", _email_confirmation_link(raw_token)
            )

        elif action == "delete_account":
            logout_user()
            database.delete_user(current_user.id)
            session.clear()
            flash("Аккаунт удалён. Мы будем скучать!", "success")
            return redirect(url_for("index"))

        if errors:
            flash("Проверьте отмеченные поля.", "error")

    return render_template(
        "account/settings.html",
        errors=errors,
        user=current_user,
        note=note,
    )
