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
from .auth import flow, tokens
from .auth.store import backend, delete_secret, get_secret, set_secret

REGISTER_URL = "https://oauth.yandex.ru/client/new"

SETUP_STEPS = f"""
Чтобы сервер получил доступ к вашим данным, Яндексу нужно знать, какое
приложение спрашивает. Приложение регистрируется один раз и бесплатно.

1. Открой {REGISTER_URL}

2. Яндекс спросит «Какое приложение хотите создать?». Подходят оба варианта,
   разница только в том, как потом делать вход:

   «Для авторизации пользователей» — Redirect URI можно задать своим,
       впиши {flow.LOCAL_REDIRECT_URI}
       Это адрес на твоём же компьютере, токен наружу не уходит.
       Вход потом: yandex-mcp login

   «Для доступа к API или отладки» — Redirect URI зафиксирован на
       {flow.MANUAL_REDIRECT_URI}
       и его нельзя изменить. Тогда Яндекс покажет код на странице,
       а его нужно вставить в терминал.
       Вход потом: yandex-mcp login --manual

3. Название — любое, например «yandex-mcp».

4. «Доступ к данным» — впиши нужные права по названию:
       Яндекс Метрика   → metrika:read
       Яндекс Вебмастер → webmaster:hosts:read-write
       Яндекс Директ    → direct:api  (нужна отдельная заявка в Директе,
                                       рассматривается до 7 дней)

5. Создай приложение и скопируй ClientID.

Client secret не нужен — используется PKCE.
"""


def _scope_for(services):
    return " ".join(flow.SERVICE_SCOPES[service] for service in services)


def command_setup(args):
    print(SETUP_STEPS)
    if not args.no_browser:
        webbrowser.open(REGISTER_URL)
    identifier = input("ClientID: ").strip()
    if not identifier:
        sys.exit("ClientID не введён")
    set_secret(flow.CLIENT_ID_ITEM, identifier)
    print(f"\nСохранено в: {backend().describe()}")
    print("Дальше: yandex-mcp login")


def command_login(args):
    if args.exchange:
        flow.exchange(args.exchange)
        return

    services = args.service or list(flow.DEFAULT_SERVICES)
    unknown = [s for s in services if s not in flow.SERVICE_SCOPES]
    if unknown:
        sys.exit(f"неизвестный сервис: {', '.join(unknown)}; "
                 f"доступны: {', '.join(flow.SERVICE_SCOPES)}")

    # один сервис — отдельный токен (least privilege), несколько — общий токен
    name = tokens.entry(services[0]) if len(services) == 1 else tokens.entry()
    try:
        flow.login(name, _scope_for(services), manual=args.manual, no_browser=args.no_browser)
        return
    except flow.ScopeRejected as error:
        reason = str(error)

    fallback = [service for service in services if service != "direct"]
    if args.service or not fallback or "direct" not in services:
        # набор запросил пользователь либо урезать больше нечего —
        # молча сужать права нельзя
        sys.exit(f"Яндекс не дал запрошенные права: {reason}\n"
                 "Проверь, какие доступы включены у приложения на "
                 "https://oauth.yandex.ru/")

    # у приложения нет direct:api — почти всегда это неодобренная заявка в Директе
    print(f"\nЯндекс не дал права на Директ: {reason}", file=sys.stderr)
    print("Вхожу без Директа. Метрика и Вебмастер заработают сразу; когда заявку "
          "на API Директа одобрят, повтори `yandex-mcp login` — доступ "
          "подхватится сам.\n", file=sys.stderr)
    flow.login(name, _scope_for(fallback), manual=args.manual, no_browser=args.no_browser)


def _token_names():
    return [tokens.entry()] + [tokens.entry(service) for service in tokens.SERVICES]


def command_status(args):
    has_client_id = bool(os.environ.get(flow.CLIENT_ID_ENV) or get_secret(flow.CLIENT_ID_ITEM))
    print(f"хранилище: {backend().describe()}")
    print(f"client_id: {'задан' if has_client_id else 'нет — выполни `yandex-mcp setup`'}")
    print()
    names = _token_names()
    found = False
    for name in names:
        info = flow.status(name)
        if not info:
            continue
        found = True
        days = info["days_left"]
        expiry = f"осталось дней: {days}" if days is not None else "срок неизвестен"
        label = "общий токен" if name == tokens.entry() else name
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
                              choices=sorted(flow.SERVICE_SCOPES),
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
