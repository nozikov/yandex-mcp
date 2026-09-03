#!/usr/bin/env python3
"""
Получение и обновление OAuth-токенов Яндекса.

Инвариант: значения секретов никогда не печатаются в stdout/stderr —
только отпечаток sha256:xxxxxxxx (как в SecretScrubber бэкенда).
Всё хранится в Keychain, на диске в открытом виде ничего не остаётся.

Подготовка (один раз, значения вводятся интерактивно):
    security add-generic-password -s yandex-oauth-client-id     -a "$USER" -w
    security add-generic-password -s yandex-oauth-client-secret -a "$USER" -w

Использование:
    yandex-oauth login  --name yandex-metrika --scope "metrika:read" --manual
    yandex-oauth login  --name yandex-direct-ro --scope "direct:api" --manual
    yandex-oauth refresh --name yandex-metrika
    yandex-oauth status  --name yandex-metrika

--manual — для приложений, у которых Redirect URI оставлен дефолтным
(https://oauth.yandex.ru/verification_code): код подтверждения показывается
на странице и вводится в терминал. Без флага код ловится на localhost:8765,
но этот адрес должен быть заранее прописан в настройках приложения.
"""

import argparse

from .oauth import exchange, login, refresh, status


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login")
    login_parser.add_argument("--name", required=True, help="префикс записей в Keychain")
    login_parser.add_argument("--scope", required=True, help="через пробел, напр. 'metrika:read'")
    login_parser.add_argument("--manual", action="store_true",
                              help="redirect на страницу verification_code, код вводится руками")
    login_parser.add_argument("--no-browser", action="store_true",
                              help="не открывать браузер, напечатать ссылку авторизации")

    exchange_parser = subparsers.add_parser("exchange")
    exchange_parser.add_argument("--code", required=True, help="код подтверждения со страницы")

    for command in ("refresh", "status"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--name", required=True)

    args = parser.parse_args()
    if args.command == "login":
        login(args.name, args.scope, args.manual, args.no_browser)
    elif args.command == "exchange":
        exchange(args.code)
    elif args.command == "refresh":
        refresh(args.name)
    else:
        status(args.name)


if __name__ == "__main__":
    main()
