import pytest

from yandex_mcp import secrets, tokens


@pytest.fixture(autouse=True)
def isolated_backend(monkeypatch, tmp_path):
    monkeypatch.setenv(secrets.KEYSTORE_ENV, "file")
    monkeypatch.setattr(secrets.FileBackend, "__init__",
                        lambda self, path=None: setattr(self, "path", str(tmp_path / "secrets.json")))
    secrets.reset_backend()
    yield
    secrets.reset_backend()


def test_service_token_prefers_dedicated_token():
    secrets.set_secret("yandex-metrika-token", "узкий")
    secrets.set_secret(tokens.UNIFIED_TOKEN, "общий")
    assert tokens.service_token("yandex-metrika") == "узкий"


def test_service_token_falls_back_to_unified_login():
    secrets.set_secret(tokens.UNIFIED_TOKEN, "общий")
    assert tokens.service_token("yandex-metrika") == "общий"


def test_service_token_error_mentions_login_and_storage():
    with pytest.raises(RuntimeError) as excinfo:
        tokens.service_token("yandex-metrika")
    message = str(excinfo.value)
    assert "yandex-mcp login" in message
    assert "хранилище" in message
