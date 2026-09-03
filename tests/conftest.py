import pytest

from yandex_mcp.auth import store


@pytest.fixture
def file_store(monkeypatch, tmp_path):
    """Изолированное файловое хранилище вместо системного.

    Тесты не должны трогать настоящий Keychain/Secret Service пользователя —
    ни на машине разработчика, ни в CI.
    """
    monkeypatch.setenv(store.KEYSTORE_ENV, "file")
    monkeypatch.setattr(
        store.FileBackend, "__init__",
        lambda self, path=None: setattr(self, "path", str(tmp_path / "secrets.json")))
    store.reset_backend()
    yield store
    store.reset_backend()
