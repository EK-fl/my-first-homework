# -*- coding: utf-8 -*-
"""
Вспомогательный скрипт: создаёт аккуратные SVG-заглушки для каталога.

Заглушки нужны, пока настоящие изображения схем не загружены.
Запуск:  python make_placeholders.py
После того как вы положите настоящие картинки, этот файл можно удалить.
"""

import os

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "images")

# Текст на заглушке (как в задании)
PLACEHOLDER_TEXT = "Добавьте изображение схемы"

# Спокойные оттенки фирменной палитры для разных карточек
TINTS = [
    ("#E8EDE6", "#A4B4A2"),  # эвкалиптовый
    ("#EDE9E2", "#C9BBA8"),  # льняной
    ("#E6E9EF", "#9BA9C4"),  # гортензиевый
    ("#EFE7E2", "#CBA695"),  # терракотовый
]


def make_placeholder(path, width, height, tint_index, label=None):
    """Рисует заглушку: мягкий фон, сетка канвы и подпись."""
    bg, line = TINTS[tint_index % len(TINTS)]

    # Шаг сетки — стилизация под канву
    step = max(width, height) // 12

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{PLACEHOLDER_TEXT}">',
        f'  <rect width="{width}" height="{height}" fill="{bg}"/>',
        # Сетка канвы
        f'  <g stroke="{line}" stroke-width="1" opacity="0.45">',
    ]
    x = step
    while x < width:
        lines.append(f'    <line x1="{x}" y1="0" x2="{x}" y2="{height}"/>')
        x += step
    y = step
    while y < height:
        lines.append(f'    <line x1="0" y1="{y}" x2="{width}" y2="{y}"/>')
        y += step
    lines.append("  </g>")

    # Центральный крестик — фирменный мотив (два простых прямоугольника)
    cx, cy = width // 2, height // 2 - 18
    s = max(18, min(width, height) // 10)  # сторона крестика
    a = s // 3                             # ширина «рукавов»
    lines += [
        f'  <g fill="{line}" opacity="0.65">',
        f'    <rect x="{cx - a // 2}" y="{cy - s // 2}" width="{a}" height="{s}"/>',
        f'    <rect x="{cx - s // 2}" y="{cy - a // 2}" width="{s}" height="{a}"/>',
        f'  </g>',
        # Подпись
        f'  <text x="{cx}" y="{cy + s * 1.8}" text-anchor="middle" '
        f'font-family="Segoe UI, Manrope, Arial, sans-serif" '
        f'font-size="{max(14, min(width, height) // 18)}" fill="#6A4C3E" '
        f'opacity="0.8">{PLACEHOLDER_TEXT}</text>',
    ]
    if label:
        lines += [
            f'  <text x="{cx}" y="{cy + s * 1.8 + max(14, min(width, height) // 14)}" '
            f'text-anchor="middle" font-family="Segoe UI, Manrope, Arial, sans-serif" '
            f'font-size="{max(11, min(width, height) // 24)}" fill="#6A4C3E" '
            f'opacity="0.55">{label}</text>',
        ]
    lines.append("</svg>")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("создан:", path)


def main():
    # Общая заглушка «изображение отсутствует»
    make_placeholder(
        os.path.join(BASE, "placeholders", "no-image.svg"), 800, 600, 0
    )

    # Заглушки для демонстрационных схем
    slugs = [
        "demo-lisitsa", "demo-sinitsa", "demo-chaynik", "demo-sad",
        "demo-kot", "demo-fonar", "demo-tsvetok",
    ]
    for i, slug in enumerate(slugs):
        make_placeholder(
            os.path.join(BASE, "patterns", f"{slug}.svg"), 800, 600, i,
            label=slug,
        )


if __name__ == "__main__":
    main()
