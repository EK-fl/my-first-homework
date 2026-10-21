# -*- coding: utf-8 -*-
"""
Демонстрационный скрипт: создаёт ТЕСТОВЫЙ фрагмент схемы 10×10 клеточек.

Это пример формата, который ожидает сайт: картинка ровно из 10 клеточек
по горизонтали и 10 по вертикали, в каждой клетке — символ схемы.
Настоящие фрагменты вы готовите сами (например, скриншотом из программы).

Запуск (создаст файл static/images/previews/demo-lisitsa-10x10.png):
    python make_preview_fragment.py

Для этого нужна библиотека Pillow:  python -m pip install pillow
Если Pillow не установлен — скрипт вежливо об этом сообщит.
"""

import os
import random

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "images", "previews")

# Символы, как в настоящих схемах вышивки
SYMBOLS = ["×", "+", "●", "○", "▲", "△", "■", "□", "◆", "✕", "◐", "◑", "⁄", "\\", "|", "-"]

# Палитра в стиле старых схем: тёмный символ на светлой клетке
INK_COLORS = ["#2E3B33", "#6A4C3E", "#3F4E63", "#7A3B2E", "#4A5A4E"]

CELL = 42  # сторона клетки в пикселях


def main():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Библиотека Pillow не установлена.")
        print("Установите её командой:  python -m pip install pillow")
        return

    width = height = CELL * 10  # ровно 10 клеточек по каждой стороне
    img = Image.new("RGB", (width, height), "#FDFBF7")
    draw = ImageDraw.Draw(img)

    # Подбираем шрифт, который умеет рисовать символы
    font = None
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(name, int(CELL * 0.62))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    # Фон клеток: очень бледная сетка, чтобы читались границы
    for col in range(10):
        for row in range(10):
            x0, y0 = col * CELL, row * CELL
            # Лёгкая шахматная подложка — так легче считать клетки
            if (col + row) % 2 == 0:
                draw.rectangle([x0, y0, x0 + CELL, y0 + CELL], fill="#F5F1E9")

    # Символы в клетках
    for col in range(10):
        for row in range(10):
            symbol = random.choice(SYMBOLS)
            color = random.choice(INK_COLORS)
            cx, cy = col * CELL + CELL / 2, row * CELL + CELL / 2
            # anchor="mm" центрирует символ по клетке
            draw.text((cx, cy), symbol, fill=color, font=font, anchor="mm")

    # Границы клеток — тонкие, но заметные
    for i in range(11):
        pos = i * CELL
        draw.line([(pos, 0), (pos, height)], fill="#B9AE9C", width=2 if i % 5 == 0 else 1)
        draw.line([(0, pos), (width, pos)], fill="#B9AE9C", width=2 if i % 5 == 0 else 1)

    os.makedirs(BASE, exist_ok=True)
    out = os.path.join(BASE, "demo-lisitsa-10x10.png")
    img.save(out)
    print("создан тестовый фрагмент 10×10:", out)
    print("Это ДЕМОНСТРАЦИЯ формата, а не настоящая схема.")


if __name__ == "__main__":
    main()
