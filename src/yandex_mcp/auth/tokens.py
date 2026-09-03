"""Имена записей в хранилище и получение токена сервиса.

Всё, чем владеет инструмент, лежит под префиксом `yandex-mcp-`: в macOS
Keychain имена глобальные, так что префикс — это и пространство имён, и
гарантия, что `logout` не заденет чужие записи.

    yandex-mcp-token            общий токен единого входа
    yandex-mcp-metrika-token    узкий токен одного сервиса
    yandex-mcp-<имя>-refresh    refresh-токен
    yandex-mcp-<имя>-expires    срок истечения
    yandex-mcp-client-id        ID приложения Яндекса
"""

from .store import backend, get_secret

PREFIX = "yandex-mcp"
SERVICES = ("metrika", "webmaster", "direct")


def entry(service=None):
    """Базовое имя записи: `yandex-mcp` или `yandex-mcp-<сервис>`."""
    return f"{PREFIX}-{service}" if service else PREFIX


def service_token(service):
    """Токен для сервиса (`metrika`, `webmaster`, `direct`).

    Сначала ищется узкий токен сервиса — его выдаёт `login --service <имя>`
    тем, кому важен least privilege. Если его нет, берётся общий токен
    единого входа.
    """
    for name in (f"{entry(service)}-token", f"{entry()}-token"):
        value = get_secret(name)
        if value:
            return value
    raise RuntimeError(
        f"нет токена для {service} — выполни `yandex-mcp login` "
        f"(хранилище: {backend().describe()})")
