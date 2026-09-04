import pytest

from yandex_mcp.tools import auth


@pytest.fixture(autouse=True)
def _clean(file_store):
    auth._pending.clear()
    yield
    auth._pending.clear()


def test_login_returns_link_and_never_the_verifier(monkeypatch):
    monkeypatch.setenv("YANDEX_MCP_CLIENT_ID", "test-client")
    text = auth.tool_yandex_login({})
    assert "https://oauth.yandex.ru/authorize" in text
    assert "code_challenge_method=S256" in text
    # code_verifier остаётся в памяти процесса и не должен утечь в ответ агенту
    assert auth._pending["verifier"] not in text


def test_login_asks_for_all_three_services_by_default(monkeypatch):
    monkeypatch.setenv("YANDEX_MCP_CLIENT_ID", "test-client")
    auth.tool_yandex_login({})
    scope = auth._pending["scope"]
    assert "metrika:read" in scope
    assert "webmaster:hostinfo" in scope
    assert "direct:api" in scope


def test_login_single_service_targets_narrow_entry(monkeypatch):
    monkeypatch.setenv("YANDEX_MCP_CLIENT_ID", "test-client")
    auth.tool_yandex_login({"services": ["metrika"]})
    assert auth._pending["entry"] == "yandex-mcp-metrika"


def test_login_rejects_unknown_service(monkeypatch):
    monkeypatch.setenv("YANDEX_MCP_CLIENT_ID", "test-client")
    with pytest.raises(RuntimeError):
        auth.tool_yandex_login({"services": ["почта"]})


def test_submit_code_without_login_is_refused():
    with pytest.raises(RuntimeError) as error:
        auth.tool_yandex_submit_code({"code": "123"})
    assert "yandex_login" in str(error.value)


def test_submit_code_stores_token_and_returns_only_fingerprint(monkeypatch):
    monkeypatch.setenv("YANDEX_MCP_CLIENT_ID", "test-client")
    auth.tool_yandex_login({"services": ["metrika"]})
    monkeypatch.setattr(auth.flow, "post_token",
                        lambda params, allow_retry_without_redirect=False: {
                            "access_token": "y0_очень_секретный", "expires_in": 3600})
    text = auth.tool_yandex_submit_code({"code": "abc"})
    assert "y0_очень_секретный" not in text
    assert "sha256:" in text
    # незавершённый вход должен быть закрыт, повторный обмен тем же кодом невозможен
    assert auth._pending == {}


def test_oauth_error_becomes_tool_error_not_process_exit(monkeypatch):
    monkeypatch.setenv("YANDEX_MCP_CLIENT_ID", "test-client")
    auth.tool_yandex_login({"services": ["metrika"]})

    def boom(params, allow_retry_without_redirect=False):
        raise auth.flow.OAuthError("OAuth отказал: invalid_grant — code expired")

    monkeypatch.setattr(auth.flow, "post_token", boom)
    with pytest.raises(RuntimeError) as error:
        auth.tool_yandex_submit_code({"code": "abc"})
    assert "code expired" in str(error.value)


def test_auth_status_reports_missing_client_id(monkeypatch):
    monkeypatch.delenv("YANDEX_MCP_CLIENT_ID", raising=False)
    text = auth.tool_yandex_auth_status({})
    assert "client_id: нет" in text
    assert "токенов нет" in text
