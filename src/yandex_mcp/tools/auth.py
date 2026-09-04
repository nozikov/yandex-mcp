"""Вход в Яндекс прямо из чата, без терминала.

Зачем отдельно от cli.py: там вход рассчитан на человека у консоли —
`input()`, печать в stdout и блокирующее ожидание redirect. В MCP-режиме
ничего этого нельзя: stdout занят протоколом, а вызов инструмента должен
вернуться быстро. Поэтому вход разбит на два шага — `yandex_login` отдаёт
ссылку, `yandex_submit_code` завершает обмен.

Секреты PKCE живут только в памяти этого процесса: перезапуск сервера
отменяет незавершённый вход, и это правильно — code_verifier не должен
переживать процесс, который его породил.
"""

import http.server
import threading

from ..auth import flow, tokens
from ..auth.callback import CallbackHandler
from ..auth.store import backend

MODES = ("manual", "localhost")

# незавершённый вход: verifier, state, куда писать токен. Только в памяти.
_pending = {}
_listener = None


def _services(arguments):
    services = arguments.get("services") or list(flow.DEFAULT_SERVICES)
    if isinstance(services, str):
        services = [services]
    unknown = [name for name in services if name not in flow.SERVICE_SCOPES]
    if unknown:
        raise RuntimeError(f"неизвестный сервис: {', '.join(unknown)}; "
                           f"доступны: {', '.join(flow.SERVICE_SCOPES)}")
    return services


def _stop_listener():
    global _listener
    if _listener is not None:
        try:
            _listener.server_close()
        except OSError:
            pass
        _listener = None


def _start_listener():
    """Поднять одноразовый приёмник redirect в фоне, не блокируя вызов инструмента."""
    global _listener
    _stop_listener()
    CallbackHandler.reset()
    _listener = http.server.HTTPServer(("127.0.0.1", flow.REDIRECT_PORT), CallbackHandler)
    _listener.timeout = 600
    threading.Thread(target=_listener.handle_request, daemon=True).start()


def tool_yandex_login(arguments):
    services = _services(arguments)
    mode = arguments.get("mode") or "manual"
    if mode not in MODES:
        raise RuntimeError(f"mode может быть {' или '.join(MODES)}")

    scope = " ".join(flow.SERVICE_SCOPES[name] for name in services)
    # один сервис — узкий токен, несколько — общий; та же логика, что в CLI
    entry = tokens.entry(services[0]) if len(services) == 1 else tokens.entry()
    redirect_uri = flow.MANUAL_REDIRECT_URI if mode == "manual" else flow.LOCAL_REDIRECT_URI

    started = flow.begin(scope, redirect_uri)
    _pending.clear()
    _pending.update({
        "entry": entry,
        "verifier": started["verifier"],
        "state": started["state"],
        "redirect_uri": redirect_uri,
        "manual": mode == "manual",
        "scope": scope,
    })

    if mode == "localhost":
        _start_listener()
        finish = ("4. Вернись сюда и вызови yandex_submit_code без аргументов — "
                  "код заберётся с localhost автоматически.")
    else:
        finish = ("4. Яндекс покажет код подтверждения. Передай его пользователю "
                  "просьбой скопировать, затем вызови yandex_submit_code с этим кодом.")

    return ("Вход в Яндекс, шаг 1 из 2.\n\n"
            f"Запрашиваемые права: {scope}\n"
            f"Токен будет записан в: {entry} ({backend().describe()})\n\n"
            "1. Покажи пользователю ссылку ниже и попроси открыть её в браузере.\n"
            "2. Ссылку НЕ открывай сам и никуда не пересылай — она одноразовая.\n"
            "3. Пользователь подтверждает доступ в Яндексе.\n"
            f"{finish}\n\n"
            f"{started['url']}\n\n"
            "Код живёт 10 минут. Если Яндекс откажет с invalid_scope — значит "
            "у приложения нет запрошенного права; чаще всего это direct:api "
            "без одобренной заявки в кабинете Директа.")


def tool_yandex_submit_code(arguments):
    if not _pending:
        raise RuntimeError("нет начатого входа — сначала вызови yandex_login")

    code = (arguments.get("code") or "").strip()
    if not code and not _pending["manual"]:
        if CallbackHandler.error:
            _pending.clear()
            _stop_listener()
            raise RuntimeError(f"Яндекс отказал: "
                               f"{CallbackHandler.error_description or CallbackHandler.error}")
        if not CallbackHandler.code:
            return ("Redirect с кодом ещё не пришёл. Попроси пользователя подтвердить "
                    "доступ в открывшейся вкладке и вызови yandex_submit_code снова.")
        if CallbackHandler.state != _pending["state"]:
            _pending.clear()
            _stop_listener()
            raise RuntimeError("state не совпал — запрос мог быть подменён, начни вход заново")
        code = CallbackHandler.code

    if not code:
        raise RuntimeError("нужен код подтверждения со страницы Яндекса")

    try:
        info = flow.complete(_pending["entry"], code, _pending["redirect_uri"],
                             _pending["verifier"], manual=_pending["manual"])
    except flow.OAuthError as error:
        raise RuntimeError(str(error))
    finally:
        _pending.clear()
        _stop_listener()

    return (f"Готово. Токен записан в {info['entry']} ({info['storage']}).\n"
            f"отпечаток: {info['fingerprint']}\n"
            f"действует до: {info['expires_on']}\n\n"
            "Инструменты Метрики, Вебмастера и Директа заработают сразу — "
            "перезапускать сервер не нужно.")


def tool_yandex_auth_status(arguments):
    lines = [f"хранилище: {backend().describe()}"]
    try:
        flow.client_id()
        lines.append("client_id: задан")
    except flow.OAuthError:
        lines.append("client_id: нет — нужен ClientID приложения Яндекса "
                     "(yandex-mcp setup в терминале или переменная YANDEX_MCP_CLIENT_ID)")

    names = [tokens.entry()] + [tokens.entry(service) for service in tokens.SERVICES]
    found = False
    for name in names:
        info = flow.status(name)
        if not info:
            continue
        found = True
        days = info["days_left"]
        expiry = f"осталось дней: {days}" if days is not None else "срок неизвестен"
        label = "общий токен" if name == tokens.entry() else name
        lines.append(f"{label}: {info['fingerprint']}, {expiry}")
    if not found:
        lines.append("токенов нет — вызови yandex_login")
    if _pending:
        lines.append(f"начат вход в {_pending['entry']}, ждём yandex_submit_code")
    return "\n".join(lines)


TOOLS = [
    {
        "name": "yandex_auth_status",
        "description": "Что уже подключено: какое хранилище секретов используется, есть ли "
                       "ClientID приложения и токены, когда они истекают. Сам токен не "
                       "показывается — только отпечаток. Вызывай первым, если какой-то "
                       "инструмент ответил «нет токена».",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_yandex_auth_status,
    },
    {
        "name": "yandex_login",
        "description": "Шаг 1 входа в Яндекс: выдаёт ссылку авторизации, которую нужно "
                       "показать пользователю. Терминал не нужен. После подтверждения "
                       "вызови yandex_submit_code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "services": {"type": "array", "items": {"type": "string"},
                             "description": "metrika, webmaster, direct; по умолчанию все три"},
                "mode": {"type": "string",
                         "description": "manual (по умолчанию) — пользователь копирует код "
                                        "со страницы Яндекса; localhost — код приходит на "
                                        "127.0.0.1:8765 сам, но приложение должно быть "
                                        "зарегистрировано с этим Redirect URI"},
            },
        },
        "handler": tool_yandex_login,
    },
    {
        "name": "yandex_submit_code",
        "description": "Шаг 2 входа: обменивает код подтверждения на токен и кладёт его "
                       "в хранилище ОС. В режиме localhost вызывается без аргументов.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string",
                         "description": "код со страницы Яндекса; в режиме localhost не нужен"},
            },
        },
        "handler": tool_yandex_submit_code,
    },
]
