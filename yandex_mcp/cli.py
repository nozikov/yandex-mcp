"""Точка входа `yandex-mcp`.

Без аргументов — MCP-сервер по stdio (так его запускает клиент, и в этом режиме
в stdout не должно попасть ничего, кроме JSON-RPC). С аргументами — команды
настройки: login / status / setup / logout.
"""

import argparse
import os
import sys
import webbrowser

from . import server
from .oauth import oauth
from .secrets import backend, delete_secret, get_secret, set_secret
from .tokens import UNIFIED_NAME

REGISTER_URL = "https://oauth.yandex.ru/client/new"

SETUP_STEPS = f"""
Чтобы сервер получил доступ к вашим данным, Яндексу нужно знать, какое
приложение спрашивает. Приложение регистрируется один раз и бесплатно.

1. Открой {REGISTER_URL}
2. Название — любое, например «yandex-mcp».
3. Платформы → «Веб-сервисы» → Redirect URI:

       {oauth.LOCAL_REDIRECT_URI}

   Это адрес на твоём же компьютере: токен никуда наружу не уходит.
4. Доступы — выбери те, что нужны:
       Яндекс Метрика   → metrika:read
       Яндекс Вебмастер → webmaster:hosts:read-write
       Яндекс Директ    → direct:api  (нужна отдельная заявка в Директе,
                                       рассматривается до 7 дней)
5. Создай приложение и скопируй ClientID.

Client secret не нужен — используется PKCE.
"""


def _scope_for(services):
    return " ".join(oauth.SERVICE_SCOPES[service] for service in services)


def command_setup(args):
    print(SETUP_STEPS)
    if not args.no_browser:
        webbrowser.open(REGISTER_URL)
    identifier = input("ClientID: ").strip()
    if not identifier:
        sys.exit("ClientID не введён")
    set_secret(oauth.CLIENT_ID_ITEM, identifier)
    print(f"\nСохранено в: {backend().describe()}")
    print("Дальше: yandex-mcp login")


def command_login(args):
    if args.exchange:
        oauth.exchange(args.exchange)
        return

    services = args.service or list(oauth.DEFAULT_SERVICES)
    unknown = [s for s in services if s not in oauth.SERVICE_SCOPES]
    if unknown:
        sys.exit(f"неизвестный сервис: {', '.join(unknown)}; "
                 f"доступны: {', '.join(oauth.SERVICE_SCOPES)}")

    # один сервис — отдельный токен (least privilege), несколько — общий токен
    name = f"yandex-{services[0]}" if len(services) == 1 else UNIFIED_NAME
    oauth.login(name, _scope_for(services), manual=args.manual, no_browser=args.no_browser)


def _token_names():
    return [UNIFIED_NAME] + [f"yandex-{service}" for service in oauth.SERVICE_SCOPES]


def command_status(args):
    has_client_id = bool(os.environ.get(oauth.CLIENT_ID_ENV) or get_secret(oauth.CLIENT_ID_ITEM))
    print(f"хранилище: {backend().describe()}")
    print(f"client_id: {'задан' if has_client_id else 'нет — выполни `yandex-mcp setup`'}")
    print()
    names = _token_names()
    found = False
    for name in names:
        info = oauth.status(name)
        if not info:
            continue
        found = True
        days = info["days_left"]
        expiry = f"осталось дней: {days}" if days is not None else "срок неизвестен"
        label = "общий токен" if name == UNIFIED_NAME else name
        print(f"{label}: {info['fingerprint']}, {expiry}")
    if not found:
        print("токенов нет — выполни `yandex-mcp login`")


def command_logout(args):
    for name in _token_names():
        for suffix in ("token", "refresh", "expires"):
            delete_secret(f"{name}-{suffix}")
    print(f"токены удалены из: {backend().describe()}")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="yandex-mcp",
        description="MCP-сервер к Яндекс Метрике, Вебмастеру и Директу. "
                    "Без аргументов запускается как MCP-сервер по stdio.",
    )
    subparsers = parser.add_subparsers(dest="command")

    setup_parser = subparsers.add_parser("setup", help="регистрация приложения Яндекса по шагам")
    setup_parser.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    setup_parser.set_defaults(handler=command_setup)

    login_parser = subparsers.add_parser("login", help="вход через браузер")
    login_parser.add_argument("--service", action="append",
                              choices=sorted(oauth.SERVICE_SCOPES),
                              help="можно повторять; по умолчанию metrika + webmaster")
    login_parser.add_argument("--manual", action="store_true",
                              help="код подтверждения вводится руками (redirect на страницу Яндекса)")
    login_parser.add_argument("--no-browser", action="store_true",
                              help="не открывать браузер, напечатать ссылку")
    login_parser.add_argument("--exchange", metavar="CODE",
                              help="завершить вход, начатый с --no-browser")
    login_parser.set_defaults(handler=command_login)

    status_parser = subparsers.add_parser("status", help="какие токены есть и где лежат")
    status_parser.set_defaults(handler=command_status)

    logout_parser = subparsers.add_parser("logout", help="удалить токены из хранилища")
    logout_parser.set_defaults(handler=command_logout)

    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        server.main()      # MCP-режим: stdout занят протоколом
        return
    # вывод команд тоже кириллический — на Windows консоль по умолчанию не в UTF-8
    server.use_utf8_stdio()
    args = build_parser().parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
