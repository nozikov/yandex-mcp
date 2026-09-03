import pytest

from yandex_mcp import cli, secrets, tokens


@pytest.fixture(autouse=True)
def isolated_backend(monkeypatch, tmp_path):
    monkeypatch.setenv(secrets.KEYSTORE_ENV, "file")
    monkeypatch.setattr(secrets.FileBackend, "__init__",
                        lambda self, path=None: setattr(self, "path", str(tmp_path / "secrets.json")))
    secrets.reset_backend()
    yield
    secrets.reset_backend()


def test_no_arguments_starts_mcp_server(monkeypatch):
    # MCP-клиент запускает `yandex-mcp` без аргументов — это должен быть stdio-сервер,
    # иначе в stdout уедет что-то кроме JSON-RPC и клиент не подключится
    started = {"yes": False}
    monkeypatch.setattr(cli.server, "main", lambda: started.__setitem__("yes", True))
    cli.main([])
    assert started["yes"] is True


def test_login_defaults_to_metrika_and_webmaster(monkeypatch):
    captured = {}

    def fake_login(name, scope, manual=False, no_browser=False):
        captured["name"] = name
        captured["scope"] = scope

    monkeypatch.setattr(cli.oauth, "login", fake_login)
    cli.main(["login"])
    assert captured["name"] == tokens.UNIFIED_NAME
    assert "metrika:read" in captured["scope"]
    assert "webmaster:hosts:read-write" in captured["scope"]
    assert "direct:api" not in captured["scope"]  # требует отдельной заявки


def test_login_single_service_gets_its_own_token(monkeypatch):
    captured = {}

    def fake_login(name, scope, manual=False, no_browser=False):
        captured["name"] = name
        captured["scope"] = scope

    monkeypatch.setattr(cli.oauth, "login", fake_login)
    cli.main(["login", "--service", "direct"])
    assert captured["name"] == "yandex-direct"
    assert captured["scope"] == "direct:api"


def test_setup_stores_client_id(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *args: "my-client-id")
    cli.main(["setup", "--no-browser"])
    assert secrets.get_secret(cli.oauth.CLIENT_ID_ITEM) == "my-client-id"


def test_status_reports_absent_tokens(capsys):
    cli.main(["status"])
    output = capsys.readouterr().out
    assert "токенов нет" in output
    assert "yandex-mcp setup" in output


def test_status_never_prints_the_token_itself(capsys):
    secrets.set_secret(f"{tokens.UNIFIED_NAME}-token", "СЕКРЕТНОЕ-ЗНАЧЕНИЕ")
    cli.main(["status"])
    output = capsys.readouterr().out
    assert "СЕКРЕТНОЕ-ЗНАЧЕНИЕ" not in output
    assert "sha256:" in output


def test_logout_removes_all_tokens(capsys):
    secrets.set_secret(f"{tokens.UNIFIED_NAME}-token", "x")
    secrets.set_secret("yandex-metrika-token", "y")
    cli.main(["logout"])
    assert secrets.get_secret(f"{tokens.UNIFIED_NAME}-token") is None
    assert secrets.get_secret("yandex-metrika-token") is None
