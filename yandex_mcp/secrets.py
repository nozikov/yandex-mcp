"""Кроссплатформенное хранилище секретов.

Порядок разрешения при чтении:
  1. переменная окружения ``YANDEX_MCP_SECRET_<ИМЯ>`` — для Docker/CI, где
     системного хранилища нет и секрет прокидывают снаружи;
  2. системное хранилище: macOS Keychain (``security``) или Linux Secret
     Service (``secret-tool`` из libsecret — GNOME Keyring, KWallet);
  3. файл ``secrets.json`` в конфиг-директории с правами 0600 — фолбэк для
     headless-серверов и Windows.

Бэкенд определяется автоматически; принудительно задаётся переменной
``YANDEX_MCP_KEYSTORE`` со значением ``keychain``, ``secret-tool`` или ``file``.
"""

import json
import os
import shutil
import subprocess
import sys

ENV_PREFIX = "YANDEX_MCP_SECRET_"
KEYSTORE_ENV = "YANDEX_MCP_KEYSTORE"
SERVICE = "yandex-mcp"


def env_name(name):
    """`yandex-metrika-token` → `YANDEX_MCP_SECRET_YANDEX_METRIKA_TOKEN`."""
    return ENV_PREFIX + name.replace("-", "_").upper()


def config_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, SERVICE)


class FileBackend:
    """JSON-файл 0600. Наименее защищённый вариант — но работает везде."""

    name = "file"

    def __init__(self, path=None):
        self.path = path or os.path.join(config_dir(), "secrets.json")

    def describe(self):
        return f"файл {self.path} (права 0600)"

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as error:
            raise RuntimeError(f"файл секретов повреждён: {self.path} ({error})")

    def _save(self, data):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
            try:
                os.chmod(directory, 0o700)
            except OSError:
                pass  # Windows: права наследуются от профиля пользователя
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with open(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

    def get(self, name):
        return self._load().get(name)

    def set(self, name, value):
        data = self._load()
        data[name] = value
        self._save(data)

    def delete(self, name):
        data = self._load()
        if data.pop(name, None) is not None:
            self._save(data)


class KeychainBackend:
    """macOS Keychain через `security`."""

    name = "keychain"

    def describe(self):
        return "macOS Keychain"

    def get(self, name):
        result = subprocess.run(
            ["security", "find-generic-password", "-s", name, "-w"],
            capture_output=True, text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def set(self, name, value):
        subprocess.run(["security", "delete-generic-password", "-s", name], capture_output=True)
        result = subprocess.run(
            ["security", "add-generic-password", "-s", name,
             "-a", os.environ.get("USER", "-"), "-w", value, "-U"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"не удалось записать {name} в Keychain")

    def delete(self, name):
        subprocess.run(["security", "delete-generic-password", "-s", name], capture_output=True)


class SecretToolBackend:
    """Linux Secret Service через `secret-tool` (libsecret).

    В отличие от macOS `security`, значение передаётся через stdin, поэтому
    секрет не виден в списке процессов.
    """

    name = "secret-tool"

    def describe(self):
        return "Linux Secret Service (secret-tool)"

    def get(self, name):
        result = subprocess.run(
            ["secret-tool", "lookup", "service", SERVICE, "key", name],
            capture_output=True, text=True,
        )
        value = result.stdout.strip()
        return value if result.returncode == 0 and value else None

    def set(self, name, value):
        result = subprocess.run(
            ["secret-tool", "store", "--label", f"{SERVICE} {name}",
             "service", SERVICE, "key", name],
            input=value, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"не удалось записать {name} через secret-tool: {result.stderr.strip()}")

    def delete(self, name):
        subprocess.run(["secret-tool", "clear", "service", SERVICE, "key", name],
                       capture_output=True)


BACKENDS = {
    FileBackend.name: FileBackend,
    KeychainBackend.name: KeychainBackend,
    SecretToolBackend.name: SecretToolBackend,
}

_backend = None


def detect_backend():
    forced = os.environ.get(KEYSTORE_ENV)
    if forced:
        if forced not in BACKENDS:
            raise RuntimeError(
                f"неизвестное значение {KEYSTORE_ENV}={forced}; "
                f"доступны: {', '.join(sorted(BACKENDS))}")
        return BACKENDS[forced]()
    if sys.platform == "darwin" and shutil.which("security"):
        return KeychainBackend()
    if shutil.which("secret-tool"):
        return SecretToolBackend()
    return FileBackend()


def backend():
    global _backend
    if _backend is None:
        _backend = detect_backend()
    return _backend


def reset_backend():
    """Сбросить определённый бэкенд — нужно тестам и после смены окружения."""
    global _backend
    _backend = None


def get_secret(name):
    from_env = os.environ.get(env_name(name))
    if from_env:
        return from_env
    return backend().get(name)


def set_secret(name, value):
    backend().set(name, value)


def delete_secret(name):
    backend().delete(name)
