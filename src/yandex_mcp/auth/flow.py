"""OAuth-флоу Яндекса: PKCE-обмен кода на токен, сохранение в хранилище секретов.

client_secret не требуется: Яндекс поддерживает PKCE (RFC 7636) для публичных
клиентов — подлинность подтверждается тем, что только этот процесс знает
code_verifier. Секрет используется, только если он явно положен в хранилище
(так работали ранние версии и так устроены агентские приложения).
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from .callback import CallbackHandler
from .store import backend, get_secret, set_secret
# именно константа, а не модуль: внутри функций `tokens` — это словарь ответа OAuth,
# и импорт модуля под тем же именем был бы затенён
from .tokens import PREFIX

CLIENT_ID_ITEM = f"{PREFIX}-client-id"
CLIENT_SECRET_ITEM = f"{PREFIX}-client-secret"
CLIENT_ID_ENV = "YANDEX_MCP_CLIENT_ID"

PENDING_FILE = os.path.join(os.path.expanduser("~"), ".cache", "yandex-mcp-pending.json")
REDIRECT_PORT = 8765
LOCAL_REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
MANUAL_REDIRECT_URI = "https://oauth.yandex.ru/verification_code"
AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
TOKEN_URL = "https://oauth.yandex.ru/token"

# права, которые запрашивает вход; Директ отдельно — его API требует одобренной
# заявки, и без неё авторизация с этим правом не пройдёт
SERVICE_SCOPES = {
    "metrika": "metrika:read",
    # у Вебмастера два права, и оба нужны: hostinfo даёт данные по сайтам,
    # verify — действия от имени владельца (в том числе переобход)
    "webmaster": "webmaster:hostinfo webmaster:verify",
    "direct": "direct:api",
}
DEFAULT_SERVICES = ("metrika", "webmaster", "direct")


class OAuthError(RuntimeError):
    """Ошибка авторизации, которую нужно показать человеку.

    Раньше здесь был sys.exit, но тот же код теперь работает и внутри MCP-сервера,
    где завершать процесс нельзя. CLI ловит это в main() и выходит с тем же текстом.
    """


class ScopeRejected(OAuthError):
    """Яндекс не дал запрошенные права — обычно у приложения их просто нет.

    Самый частый случай: `direct:api` без одобренной заявки в кабинете Директа.
    Вызывающий может повторить вход с меньшим набором прав.
    """


def fingerprint(value):
    if not value:
        return "sha256:none"
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()[:8]


def client_id():
    """ID приложения: переменная окружения, затем хранилище секретов."""
    value = os.environ.get(CLIENT_ID_ENV) or get_secret(CLIENT_ID_ITEM)
    if not value:
        raise OAuthError(
            "не задан client_id приложения Яндекса.\n"
            "Выполни `yandex-mcp setup` — оно проведёт по шагам регистрации,\n"
            f"либо передай готовый через {CLIENT_ID_ENV}.")
    return value


def post_token(params, allow_retry_without_redirect=False):
    body = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # тело ошибки Яндекса может содержать эхо переданных параметров — не печатаем его целиком
        raw = error.read().decode(errors="replace")
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            payload = {}
        description = payload.get("error_description", "")
        # часть приложений не принимает redirect_uri в обмене кода — пробуем без него
        if allow_retry_without_redirect and "redirect" in description.lower():
            retried = dict(params)
            retried.pop("redirect_uri", None)
            return post_token(retried)
        raise OAuthError(f"OAuth отказал: {payload.get('error', 'unknown')} — "
                         f"{description or 'без описания'}")
    except urllib.error.URLError as error:
        raise OAuthError(f"oauth.yandex.ru недоступен ({error.reason}) — повтори команду")


def store_tokens(name, tokens):
    """Записать токены в хранилище. Ничего не печатает — годится и для MCP-режима.

    Возвращает только отпечатки и срок: сам токен наружу не отдаётся никогда.
    """
    set_secret(f"{name}-token", tokens["access_token"])
    if tokens.get("refresh_token"):
        set_secret(f"{name}-refresh", tokens["refresh_token"])
    expires_at = int(time.time()) + int(tokens.get("expires_in", 0))
    set_secret(f"{name}-expires", str(expires_at))
    return {
        "entry": name,
        "fingerprint": fingerprint(tokens["access_token"]),
        "refresh_fingerprint": fingerprint(tokens.get("refresh_token")),
        "expires_at": expires_at,
        "expires_on": time.strftime("%Y-%m-%d", time.localtime(expires_at)),
        "storage": backend().describe(),
    }


def save_tokens(name, tokens):
    info = store_tokens(name, tokens)
    print(f"access_token  {info['fingerprint']}")
    print(f"refresh_token {info['refresh_fingerprint']}")
    print(f"истекает      {info['expires_on']}")
    print(f"\nсохранено в: {info['storage']}")


def _token_request_params(code, redirect_uri, verifier):
    params = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id(),
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    secret = get_secret(CLIENT_SECRET_ITEM)
    if secret:  # PKCE секрета не требует, но агентское приложение может его иметь
        params["client_secret"] = secret
    return params


def begin(scope, redirect_uri):
    """Собрать ссылку авторизации и одноразовые секреты PKCE.

    Отделено от login(), потому что тем же самым пользуется вход из чата
    (tools/auth.py), где нет ни терминала, ни браузера под рукой.
    """
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    state = secrets.token_urlsafe(16)

    url = AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id(),
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return {"url": url, "verifier": verifier, "state": state, "redirect_uri": redirect_uri}


def complete(name, code, redirect_uri, verifier, manual=False):
    """Обменять код на токен и молча положить в хранилище."""
    tokens = post_token(_token_request_params(code, redirect_uri, verifier),
                        allow_retry_without_redirect=manual)
    return store_tokens(name, tokens)


def login(name, scope, manual=False, no_browser=False):
    redirect_uri = MANUAL_REDIRECT_URI if manual else LOCAL_REDIRECT_URI
    started = begin(scope, redirect_uri)
    url, verifier, state = started["url"], started["verifier"], started["state"]

    if no_browser:
        # verifier переживает завершение процесса — обмен делается командой --exchange
        os.makedirs(os.path.dirname(PENDING_FILE), exist_ok=True)
        with open(os.open(PENDING_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as pending:
            json.dump({"name": name, "verifier": verifier,
                       "redirect_uri": redirect_uri, "manual": manual}, pending)
        print(f"AUTH_URL {url}", flush=True)
        print("дальше: yandex-mcp login --exchange <код со страницы>")
        return

    print(f"Открываю браузер. Запрашиваемые права: {scope}")
    webbrowser.open(url)

    if manual:
        print("\nПодтверди доступ — на странице появится код подтверждения.")
        print("Вставь его сюда (код одноразовый, живёт 10 минут):")
        code = input("код: ").strip()
        if not code:
            raise OAuthError("код не введён")
    else:
        print(f"Жду подтверждения на {LOCAL_REDIRECT_URI} …")
        CallbackHandler.reset()
        server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), CallbackHandler)
        server.timeout = 180
        server.handle_request()
        if CallbackHandler.error:
            # приложению не выдано запрошенное право — вызывающий может
            # повторить вход с меньшим набором
            raise ScopeRejected(CallbackHandler.error_description or CallbackHandler.error)
        if not CallbackHandler.code:
            raise OAuthError("код авторизации не получен")
        if CallbackHandler.state != state:
            raise OAuthError("state не совпал — запрос мог быть подменён, повтори")
        code = CallbackHandler.code

    tokens = post_token(_token_request_params(code, redirect_uri, verifier),
                        allow_retry_without_redirect=manual)
    save_tokens(name, tokens)


def exchange(code):
    if not os.path.exists(PENDING_FILE):
        raise OAuthError("нет незавершённой авторизации — сначала `yandex-mcp login --no-browser`")
    with open(PENDING_FILE) as pending_file:
        pending = json.load(pending_file)

    tokens = post_token(
        _token_request_params(code, pending["redirect_uri"], pending["verifier"]),
        allow_retry_without_redirect=pending.get("manual", False))

    os.remove(PENDING_FILE)
    save_tokens(pending["name"], tokens)


def refresh(name):
    refresh_token = get_secret(f"{name}-refresh")
    if not refresh_token:
        raise OAuthError(f"нет refresh-токена для {name} — выполни `yandex-mcp login` заново")
    params = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id(),
    }
    secret = get_secret(CLIENT_SECRET_ITEM)
    if secret:
        params["client_secret"] = secret
    else:
        # обновление токена у Яндекса требует секрет; у PKCE-приложения его нет,
        # но access_token живёт около года — проще авторизоваться заново
        print("client_secret не задан (PKCE-приложение) — если Яндекс откажет, "
              "выполни `yandex-mcp login` заново", file=sys.stderr)
    save_tokens(name, post_token(params))


def status(name):
    token = get_secret(f"{name}-token")
    if not token:
        return None
    expires_at = int(get_secret(f"{name}-expires") or 0)
    days_left = (expires_at - int(time.time())) // 86400 if expires_at else None
    return {"fingerprint": fingerprint(token), "days_left": days_left}
