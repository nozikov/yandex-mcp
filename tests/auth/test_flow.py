import urllib.error

import pytest

from yandex_mcp.auth import flow


class _FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, body):
        super().__init__("https://flow.yandex.ru/token", 502, "Bad Gateway", {}, None)
        self._body = body

    def read(self):
        return self._body


def test_post_token_exits_cleanly_on_non_json_error_body(monkeypatch):
    # регрессия: json.loads(error.read().decode() or "{}") без try/except падал
    # json.JSONDecodeError, если прокси/балансировщик перед flow.yandex.ru отдаёт
    # HTML-страницу ошибки вместо JSON — пользователь видел трейсбек вместо sys.exit
    def fake_urlopen(request, timeout=30):
        raise _FakeHTTPError(b"<html>502 Bad Gateway</html>")

    monkeypatch.setattr(flow.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit):
        flow.post_token({"grant_type": "authorization_code", "code": "x"})


def test_post_token_surfaces_yandex_error_description(monkeypatch, capsys):
    def fake_urlopen(request, timeout=30):
        raise _FakeHTTPError(b'{"error": "invalid_grant", "error_description": "code expired"}')

    monkeypatch.setattr(flow.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit) as excinfo:
        flow.post_token({"grant_type": "authorization_code", "code": "x"})
    assert "code expired" in str(excinfo.value)
