import json
import os
import stat
import sys

import pytest

from yandex_mcp import secrets


@pytest.fixture(autouse=True)
def isolated_backend(monkeypatch, tmp_path):
    """Каждый тест — свой файловый бэкенд, без системного хранилища."""
    monkeypatch.setenv(secrets.KEYSTORE_ENV, "file")
    monkeypatch.setattr(secrets.FileBackend, "__init__",
                        lambda self, path=None: setattr(self, "path", str(tmp_path / "secrets.json")))
    secrets.reset_backend()
    yield
    secrets.reset_backend()


def test_env_name_mapping():
    assert secrets.env_name("yandex-metrika-token") == "YANDEX_MCP_SECRET_YANDEX_METRIKA_TOKEN"


def test_file_backend_roundtrip():
    secrets.set_secret("yandex-token", "abc123")
    assert secrets.get_secret("yandex-token") == "abc123"


def test_file_backend_delete():
    secrets.set_secret("yandex-token", "abc123")
    secrets.delete_secret("yandex-token")
    assert secrets.get_secret("yandex-token") is None


def test_missing_secret_returns_none():
    assert secrets.get_secret("нет-такого") is None


def test_env_var_wins_over_stored_value(monkeypatch):
    secrets.set_secret("yandex-token", "из-файла")
    monkeypatch.setenv(secrets.env_name("yandex-token"), "из-окружения")
    assert secrets.get_secret("yandex-token") == "из-окружения"


@pytest.mark.skipif(os.name == "nt", reason="права POSIX неприменимы к Windows")
def test_file_written_with_owner_only_permissions():
    secrets.set_secret("yandex-token", "abc123")
    mode = os.stat(secrets.backend().path).st_mode
    assert stat.S_IMODE(mode) == 0o600
    assert not mode & stat.S_IRGRP
    assert not mode & stat.S_IROTH


def test_corrupted_file_raises_readable_error():
    path = secrets.backend().path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{это не json")
    with pytest.raises(RuntimeError, match="повреждён"):
        secrets.get_secret("yandex-token")


def test_unknown_forced_backend_raises(monkeypatch):
    monkeypatch.setenv(secrets.KEYSTORE_ENV, "нет-такого-бэкенда")
    secrets.reset_backend()
    with pytest.raises(RuntimeError, match="неизвестное значение"):
        secrets.get_secret("yandex-token")


def test_autodetect_prefers_keychain_on_macos(monkeypatch):
    monkeypatch.delenv(secrets.KEYSTORE_ENV, raising=False)
    monkeypatch.setattr(secrets.sys, "platform", "darwin")
    monkeypatch.setattr(secrets.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert secrets.detect_backend().name == "keychain"


def test_autodetect_uses_secret_tool_on_linux(monkeypatch):
    monkeypatch.delenv(secrets.KEYSTORE_ENV, raising=False)
    monkeypatch.setattr(secrets.sys, "platform", "linux")
    monkeypatch.setattr(secrets.shutil, "which",
                        lambda name: "/usr/bin/secret-tool" if name == "secret-tool" else None)
    assert secrets.detect_backend().name == "secret-tool"


def test_autodetect_falls_back_to_file(monkeypatch):
    monkeypatch.delenv(secrets.KEYSTORE_ENV, raising=False)
    monkeypatch.setattr(secrets.sys, "platform", "win32")
    monkeypatch.setattr(secrets.shutil, "which", lambda name: None)
    assert secrets.detect_backend().name == "file"


def test_stored_file_is_valid_json_with_all_keys():
    secrets.set_secret("a-token", "1")
    secrets.set_secret("b-token", "2")
    with open(secrets.backend().path, encoding="utf-8") as handle:
        assert json.load(handle) == {"a-token": "1", "b-token": "2"}
