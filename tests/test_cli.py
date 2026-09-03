import pytest

from yandex_mcp import cli
from yandex_mcp.auth import store, tokens


@pytest.fixture(autouse=True)
def _isolated(file_store):
    """Все тесты модуля работают на временном файловом хранилище."""


def test_no_arguments_starts_mcp_server(monkeypatch):
    # MCP-клиент запускает `yandex-mcp` без аргументов — это должен быть stdio-сервер,
    # иначе в stdout уедет что-то кроме JSON-RPC и клиент не подключится
    started = {"yes": False}
    monkeypatch.setattr(cli.server, "main", lambda: started.__setitem__("yes", True))
    cli.main([])
    assert started["yes"] is True


def test_login_asks_for_everything_by_default(monkeypatch):
    # что доступно на самом деле, решает панель Яндекса, а не флаги здесь:
    # просим всё, что приложение может дать
    captured = {}

    def fake_login(name, scope, manual=False, no_browser=False):
        captured["name"] = name
        captured["scope"] = scope

    monkeypatch.setattr(cli.flow, "login", fake_login)
    cli.main(["login"])
    assert captured["name"] == tokens.entry()
    assert "metrika:read" in captured["scope"]
    assert "webmaster:hosts:read-write" in captured["scope"]
    assert "direct:api" in captured["scope"]


def test_login_falls_back_without_direct_when_not_approved(monkeypatch, capsys):
    # у приложения нет direct:api (заявка в Директе не одобрена) — вход не должен
    # проваливаться целиком, Метрика и Вебмастер обязаны заработать сразу
    attempts = []

    def fake_login(name, scope, manual=False, no_browser=False):
        attempts.append(scope)
        if len(attempts) == 1:
            raise cli.flow.ScopeRejected("Не удалось определить список запрашиваемых доступов")

    monkeypatch.setattr(cli.flow, "login", fake_login)
    cli.main(["login"])

    assert len(attempts) == 2
    assert "direct:api" in attempts[0]
    assert "direct:api" not in attempts[1]
    assert "metrika:read" in attempts[1]
    assert "Директ" in capsys.readouterr().err


def test_login_does_not_silently_narrow_an_explicit_service(monkeypatch):
    def fake_login(name, scope, manual=False, no_browser=False):
        raise cli.flow.ScopeRejected("нет прав")

    monkeypatch.setattr(cli.flow, "login", fake_login)
    with pytest.raises(SystemExit):
        cli.main(["login", "--service", "direct"])


def test_login_single_service_gets_its_own_token(monkeypatch):
    captured = {}

    def fake_login(name, scope, manual=False, no_browser=False):
        captured["name"] = name
        captured["scope"] = scope

    monkeypatch.setattr(cli.flow, "login", fake_login)
    cli.main(["login", "--service", "direct"])
    assert captured["name"] == "yandex-mcp-direct"
    assert captured["scope"] == "direct:api"


def test_setup_stores_client_id(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *args: "my-client-id")
    cli.main(["setup", "--no-browser"])
    assert store.get_secret(cli.flow.CLIENT_ID_ITEM) == "my-client-id"


def test_status_reports_absent_tokens(capsys):
    cli.main(["status"])
    output = capsys.readouterr().out
    assert "токенов нет" in output
    assert "yandex-mcp setup" in output


def test_status_never_prints_the_token_itself(capsys):
    store.set_secret(f"{tokens.entry()}-token", "СЕКРЕТНОЕ-ЗНАЧЕНИЕ")
    cli.main(["status"])
    output = capsys.readouterr().out
    assert "СЕКРЕТНОЕ-ЗНАЧЕНИЕ" not in output
    assert "sha256:" in output


def test_logout_removes_all_tokens(capsys):
    store.set_secret(f"{tokens.entry()}-token", "x")
    store.set_secret(f"{tokens.entry('metrika')}-token", "y")
    cli.main(["logout"])
    assert store.get_secret(f"{tokens.entry()}-token") is None
    assert store.get_secret(f"{tokens.entry('metrika')}-token") is None
