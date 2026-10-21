# -*- coding: utf-8 -*-
"""
setup_admin.py — разовая настройка доступа в административную панель.

Запускать из папки проекта:

    python setup_admin.py

Команда спросит логин и пароль. Пароль при вводе не отображается на экране
(это нормально — так его никто не подсмотрит). В базе сохраняется ТОЛЬКО
хеш пароля, восстановить из него сам пароль невозможно.

Можно также запустить без вопросов, указав данные сразу:

    python setup_admin.py --username elena --password "очень-секретный-пароль"

Важно:
  * В исходном коде сайта нет и не будет готового пароля.
  * Эта команда не создаёт «демонстрационных» паролей.
  * Повторный запуск меняет логин и пароль существующего администратора.
"""

import argparse
import getpass
import sys

import config
import database
from security import MIN_PASSWORD_LENGTH, hash_password, password_problems


def ask_username(default=""):
    """Спрашивает логин. Пустой ввод — берём значение по умолчанию."""
    prompt = f"Логин администратора [{default}]: " if default else "Логин администратора: "
    while True:
        value = input(prompt).strip()
        if not value:
            value = default
        if not value:
            print("  Логин не может быть пустым. Попробуйте снова.")
            continue
        if len(value) < 3:
            print("  Логин слишком короткий — минимум 3 символа.")
            continue
        if " " in value:
            print("  В логине не должно быть пробелов.")
            continue
        return value


def ask_password():
    """
    Дважды спрашивает пароль и проверяет его надёжность.
    getpass скрывает ввод — пароль не появится на экране.
    """
    while True:
        try:
            password = getpass.getpass(
                f"Пароль (минимум {MIN_PASSWORD_LENGTH} символов, ввод скрыт): "
            )
            again = getpass.getpass("Повторите пароль: ")
        except (KeyboardInterrupt, EOFError):
            print("\nНастройка отменена.")
            sys.exit(1)

        if password != again:
            print("  Пароли не совпали. Попробуйте снова.\n")
            continue

        problems = password_problems(password)
        if problems:
            print(f"  Пароль слабый: {', '.join(problems)}. Попробуйте снова.\n")
            continue

        return password


def main():
    parser = argparse.ArgumentParser(
        description="Настройка логина и пароля администратора сайта «Ехидные крестики»",
    )
    parser.add_argument("--username", help="логин администратора")
    parser.add_argument(
        "--password",
        help="пароль администратора (если не указан — команда спросит его скрытно)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("НАСТРОЙКА ДОСТУПА В АДМИНИСТРАТИВНУЮ ПАНЕЛЬ")
    print("=" * 70)

    # Создаём таблицы, если базы ещё нет
    database.init_db()

    existing = database.get_admin()
    if existing:
        print(f"Сейчас в базе есть администратор: «{existing['username']}»")
        print("Продолжение изменит его логин и пароль.")
        print()
    else:
        print("Администратор ещё не заведён. Придумайте логин и пароль.")
        print()

    # Логин
    if args.username:
        username = args.username.strip()
        if len(username) < 3 or " " in username:
            print("Ошибка: логин должен быть не короче 3 символов и без пробелов.")
            sys.exit(1)
    else:
        username = ask_username(existing["username"] if existing else "")

    # Пароль
    if args.password:
        password = args.password
        problems = password_problems(password)
        if problems:
            print(f"Ошибка: пароль слабый — {', '.join(problems)}.")
            print("Придумайте более надёжный пароль.")
            sys.exit(1)
    else:
        password = ask_password()

    # Сохраняем только хеш — сам пароль нигде не записывается
    database.set_admin(username, hash_password(password))

    # Резервная копия базы после важного изменения
    backup = database.backup_database()

    print()
    print("=" * 70)
    print("ГОТОВО!")
    print(f"  Логин: {username}")
    print("  Пароль сохранён в виде хеша — восстановить его нельзя, только сменить.")
    if backup:
        print(f"  Резервная копия базы: {backup}")
    print()
    print("Дальше:")
    print("  1. Запустите сайт:            python app.py")
    print("  2. Откройте адрес входа:      http://127.0.0.1:5000/admin/login")
    print("  3. Введите логин и пароль.")
    print()
    print("Чтобы сменить пароль позже — просто запустите эту команду снова.")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nНастройка отменена.")
        sys.exit(1)
