"""Логика OAuth-флоу: PKCE-обмен кода на токены, сохранение в Keychain."""

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
from .keychain import CLIENT_ID_ITEM, CLIENT_SECRET_ITEM, fingerprint, keychain_get, keychain_set

PENDING_FILE = os.path.expanduser("~/.cache/yandex-oauth-pending.json")
REDIRECT_PORT = 8765
LOCAL_REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
MANUAL_REDIRECT_URI = "https://oauth.yandex.ru/verification_code"
AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
TOKEN_URL = "https://oauth.yandex.ru/token"


def post_token(params, allow_retry_without_redirect=False):
    body = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # тело ошибки Яндекса может содержать эхо переданных параметров — не печатаем его целиком
        payload = json.loads(error.read().decode() or "{}")
        description = payload.get("error_description", "")
        # часть приложений не принимает redirect_uri в обмене кода — пробуем без него
        if allow_retry_without_redirect and "redirect" in description.lower():
            retried = dict(params)
            retried.pop("redirect_uri", None)
            return post_token(retried)
        sys.exit(f"OAuth отказал: {payload.get('error', 'unknown')} — "
                 f"{description or 'без описания'}")
    except urllib.error.URLError as error:
        sys.exit(f"oauth.yandex.ru недоступен ({error.reason}) — повтори команду")


def save_tokens(name, tokens):
    keychain_set(f"{name}-token", tokens["access_token"])
    if tokens.get("refresh_token"):
        keychain_set(f"{name}-refresh", tokens["refresh_token"])
    expires_at = int(time.time()) + int(tokens.get("expires_in", 0))
    keychain_set(f"{name}-expires", str(expires_at))
    print(f"access_token  {fingerprint(tokens['access_token'])}")
    print(f"refresh_token {fingerprint(tokens.get('refresh_token'))}")
    print(f"истекает      {time.strftime('%Y-%m-%d', time.localtime(expires_at))}")
    print(f"\nKeychain: {name}-token, {name}-refresh, {name}-expires")


def login(name, scope, manual, no_browser=False):
    client_id = keychain_get(CLIENT_ID_ITEM)
    client_secret = keychain_get(CLIENT_SECRET_ITEM)
    redirect_uri = MANUAL_REDIRECT_URI if manual else LOCAL_REDIRECT_URI

    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    state = secrets.token_urlsafe(16)

    url = AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })

    if no_browser:
        # verifier переживает завершение процесса — обмен делается командой exchange
        os.makedirs(os.path.dirname(PENDING_FILE), exist_ok=True)
        with open(os.open(PENDING_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as pending:
            json.dump({"name": name, "verifier": verifier,
                       "redirect_uri": redirect_uri, "manual": manual}, pending)
        print(f"AUTH_URL {url}", flush=True)
        print("дальше: yandex-oauth exchange --code <код со страницы>")
        return

    print(f"Открываю браузер. Запрашиваемые права: {scope}")
    webbrowser.open(url)

    if manual:
        print("\nПодтверди доступ — на странице появится код подтверждения.")
        print("Вставь его сюда (код одноразовый, живёт 10 минут):")
        code = input("код: ").strip()
        if not code:
            sys.exit("код не введён")
    else:
        server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), CallbackHandler)
        server.timeout = 180
        server.handle_request()
        if not CallbackHandler.code:
            sys.exit("код авторизации не получен")
        if CallbackHandler.state != state:
            sys.exit("state не совпал — запрос мог быть подменён, повтори")
        code = CallbackHandler.code

    tokens = post_token({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }, allow_retry_without_redirect=manual)
    save_tokens(name, tokens)


def exchange(code):
    if not os.path.exists(PENDING_FILE):
        sys.exit("нет незавершённой авторизации — сначала login --no-browser")
    with open(PENDING_FILE) as pending_file:
        pending = json.load(pending_file)

    tokens = post_token({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": keychain_get(CLIENT_ID_ITEM),
        "client_secret": keychain_get(CLIENT_SECRET_ITEM),
        "redirect_uri": pending["redirect_uri"],
        "code_verifier": pending["verifier"],
    }, allow_retry_without_redirect=pending.get("manual", False))

    os.remove(PENDING_FILE)
    save_tokens(pending["name"], tokens)


def refresh(name):
    refresh_token = keychain_get(f"{name}-refresh")
    tokens = post_token({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": keychain_get(CLIENT_ID_ITEM),
        "client_secret": keychain_get(CLIENT_SECRET_ITEM),
    })
    save_tokens(name, tokens)


def status(name):
    token = keychain_get(f"{name}-token", required=False)
    if not token:
        sys.exit(f"токен {name} не найден в Keychain")
    expires_at = int(keychain_get(f"{name}-expires", required=False) or 0)
    days_left = (expires_at - int(time.time())) // 86400
    print(f"{name}: {fingerprint(token)}, осталось дней: {days_left}")
