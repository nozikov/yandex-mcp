import json
import os
import stat
import sys

import pytest

from yandex_mcp.auth import store


@pytest.fixture(autouse=True)
def _isolated(file_store):
    """Все тесты модуля работают на временном файловом хранилище."""


def test_env_name_mapping():
    assert store.env_name("yandex-mcp-metrika-token") == "YANDEX_MCP_SECRET_METRIKA_TOKEN"


def test_file_backend_roundtrip():
    store.set_secret("yandex-mcp-token", "abc123")
    assert store.get_secret("yandex-mcp-token") == "abc123"


def test_file_backend_delete():
    store.set_secret("yandex-mcp-token", "abc123")
    store.delete_secret("yandex-mcp-token")
    assert store.get_secret("yandex-mcp-token") is None


def test_missing_secret_returns_none():
    assert store.get_secret("нет-такого") is None


def test_env_var_wins_over_stored_value(monkeypatch):
    store.set_secret("yandex-mcp-token", "из-файла")
    monkeypatch.setenv(store.env_name("yandex-mcp-token"), "из-окружения")
    assert store.get_secret("yandex-mcp-token") == "из-окружения"


@pytest.mark.skipif(os.name == "nt", reason="права POSIX неприменимы к Windows")
def test_file_written_with_owner_only_permissions():
    store.set_secret("yandex-mcp-token", "abc123")
    mode = os.stat(store.backend().path).st_mode
    assert stat.S_IMODE(mode) == 0o600
    assert not mode & stat.S_IRGRP
    assert not mode & stat.S_IROTH


def test_corrupted_file_raises_readable_error():
    path = store.backend().path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{это не json")
    with pytest.raises(RuntimeError, match="повреждён"):
        store.get_secret("yandex-mcp-token")


def test_unknown_forced_backend_raises(monkeypatch):
    monkeypatch.setenv(store.KEYSTORE_ENV, "нет-такого-бэкенда")
    store.reset_backend()
    with pytest.raises(RuntimeError, match="неизвестное значение"):
        store.get_secret("yandex-mcp-token")


def test_autodetect_prefers_keychain_on_macos(monkeypatch):
    monkeypatch.delenv(store.KEYSTORE_ENV, raising=False)
    monkeypatch.setattr(store.sys, "platform", "darwin")
    monkeypatch.setattr(store.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert store.detect_backend().name == "keychain"


def test_autodetect_uses_secret_tool_on_linux(monkeypatch):
    monkeypatch.delenv(store.KEYSTORE_ENV, raising=False)
    monkeypatch.setattr(store.sys, "platform", "linux")
    monkeypatch.setattr(store.shutil, "which",
                        lambda name: "/usr/bin/secret-tool" if name == "secret-tool" else None)
    assert store.detect_backend().name == "secret-tool"


def test_autodetect_falls_back_to_file(monkeypatch):
    monkeypatch.delenv(store.KEYSTORE_ENV, raising=False)
    monkeypatch.setattr(store.sys, "platform", "win32")
    monkeypatch.setattr(store.shutil, "which", lambda name: None)
    assert store.detect_backend().name == "file"


def test_stored_file_is_valid_json_with_all_keys():
    store.set_secret("a-token", "1")
    store.set_secret("b-token", "2")
    with open(store.backend().path, encoding="utf-8") as handle:
        assert json.load(handle) == {"a-token": "1", "b-token": "2"}
