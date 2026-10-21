# -*- coding: utf-8 -*-
"""
public_content.py — публичные блоки: галерея отшивов и отзывы.

Здесь живут маршруты, которые видят все посетители:

    /gallery        — все опубликованные готовые работы
    /gallery/<id>   — одна работа крупно
    /reviews        — все отзывы с фильтрами

Формы создания отшивов и отзывов находятся в личном кабинете (users.py),
а их проверка — в админ-панели (admin.py).
"""

from flask import Blueprint, abort, render_template, request

import config
import database

public_content = Blueprint("public_content", __name__)


def _project_for_view(project):
    """Готовит работу для шаблона: только безопасные пути к фотографиям."""
    from app import _safe_image_path
    images = [img for img in project["images"] if _safe_image_path(img)]
    view = dict(project)
    view["visible_images"] = images
    view["cover"] = images[0] if images else ""
    # Фотографии пользователей лежат в static/images/projects/ —
    # их показывает обычная страница.
    return view


@public_content.route("/gallery")
def gallery():
    """Все опубликованные готовые работы."""
    projects = [_project_for_view(p) for p in database.list_public_projects()]
    projects = [p for p in projects if p["visible_images"]]
    settings = database.get_settings()
    return render_template(
        "gallery.html",
        projects=projects,
        title=settings.get("gallery_title", "Хвастики без скромности"),
        subtitle=settings.get("gallery_subtitle", ""),
        empty_message=settings.get("gallery_empty_message", ""),
    )


@public_content.route("/gallery/<int:project_id>")
def project_page(project_id):
    """Одна готовая работа крупно с рассказом автора."""
    project = database.get_project(project_id)
    if project is None:
        abort(404)
    # Показываем только одобренные работы с согласием на публикацию
    if project["status"] != "approved" or not project["publish_consent"]:
        abort(404)

    project = _project_for_view(project)
    # Загружаем фотографии работы
    project["images"] = [img["path"] for img in database.get_project_images(project_id)]
    project = _project_for_view(project)

    related = [
        _project_for_view(p) for p in database.list_public_projects(limit=8)
        if p["id"] != project_id
    ][:3]

    return render_template("gallery_project.html", project=project, related=related)


@public_content.route("/reviews")
def reviews():
    """
    Все отзывы с фильтрами.

    Показываются ТОЛЬКО опубликованные отзывы — как и на главной.
    """
    category = request.args.get("category") or ""
    pattern_id = request.args.get("pattern", type=int)
    if category not in dict(config.REVIEW_CATEGORIES):
        category = ""
    if category != "pattern":
        pattern_id = None

    items = database.list_reviews(
        status="approved", category=category, pattern_id=pattern_id
    )
    settings = database.get_settings()

    return render_template(
        "reviews.html",
        reviews=items,
        categories=config.REVIEW_CATEGORIES,
        active_category=category,
        active_pattern=pattern_id,
        patterns=database.list_published_patterns(),
        stats=database.review_rating_stats(pattern_id if category == "pattern" else None),
        title=settings.get("reviews_title", "Ваши впечатления"),
        subtitle=settings.get("reviews_subtitle", ""),
        empty_message=settings.get("reviews_empty_message", ""),
    )
