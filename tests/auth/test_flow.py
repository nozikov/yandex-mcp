import urllib.error

import pytest

from yandex_mcp.auth import flow


@pytest.fixture(autouse=True)
def _isolated(file_store, monkeypatch):
    """Ни один тест модуля не должен видеть системное хранилище и настоящий client_id.

    Регрессия: тест begin() проходил на машине разработчика, где ClientID лежит
    в Keychain, и падал в CI на чистой системе.
    """
    monkeypatch.delenv("YANDEX_MCP_CLIENT_ID", raising=False)


class _FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, body):
        super().__init__("https://oauth.yandex.ru/token", 502, "Bad Gateway", {}, None)
        self._body = body

    def read(self):
        return self._body


def test_post_token_raises_cleanly_on_non_json_error_body(monkeypatch):
    # регрессия: json.loads(error.read().decode() or "{}") без try/except падал
    # json.JSONDecodeError, если прокси/балансировщик перед oauth.yandex.ru отдаёт
    # HTML-страницу ошибки вместо JSON — пользователь видел трейсбек
    def fake_urlopen(request, timeout=30):
        raise _FakeHTTPError(b"<html>502 Bad Gateway</html>")

    monkeypatch.setattr(flow.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(flow.OAuthError):
        flow.post_token({"grant_type": "authorization_code", "code": "x"})


def test_post_token_surfaces_yandex_error_description(monkeypatch, capsys):
    def fake_urlopen(request, timeout=30):
        raise _FakeHTTPError(b'{"error": "invalid_grant", "error_description": "code expired"}')

    monkeypatch.setattr(flow.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(flow.OAuthError) as excinfo:
        flow.post_token({"grant_type": "authorization_code", "code": "x"})
    assert "code expired" in str(excinfo.value)


def test_begin_requires_client_id():
    # на чистой машине приложение ещё не зарегистрировано — это должно быть
    # понятной ошибкой, а не пустым client_id в ссылке авторизации
    with pytest.raises(flow.OAuthError) as error:
        flow.begin("metrika:read", flow.MANUAL_REDIRECT_URI)
    assert "client_id" in str(error.value)


def test_begin_builds_pkce_url_without_leaking_verifier(monkeypatch):
    monkeypatch.setenv("YANDEX_MCP_CLIENT_ID", "test-client")
    started = flow.begin("metrika:read", flow.MANUAL_REDIRECT_URI)
    assert "code_challenge_method=S256" in started["url"]
    assert "response_type=code" in started["url"]
    # verifier остаётся только у нас: в ссылку уходит challenge, а не он сам
    assert started["verifier"] not in started["url"]
    assert started["state"] in started["url"]


def test_store_tokens_returns_fingerprint_not_token():
    info = flow.store_tokens("yandex-mcp-test",
                             {"access_token": "y0_секретное", "expires_in": 3600})
    assert info["fingerprint"].startswith("sha256:")
    assert "секретное" not in repr(info)
