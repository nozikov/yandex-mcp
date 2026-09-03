"""Получение OAuth-токена сервиса из хранилища секретов."""

from .secrets import backend, get_secret

# токен, выданный единым входом `yandex-mcp login` — общий для всех сервисов
UNIFIED_NAME = "yandex"
UNIFIED_TOKEN = f"{UNIFIED_NAME}-token"


def service_token(service):
    """Токен для сервиса (`yandex-metrika`, `yandex-webmaster`, `yandex-direct`).

    Сначала ищется отдельный токен сервиса — он выдаётся `login --service <имя>`
    и нужен тем, кому важен least privilege. Если его нет, берётся общий токен
    единого входа.
    """
    for candidate in (f"{service}-token", UNIFIED_TOKEN):
        value = get_secret(candidate)
        if value:
            return value
    raise RuntimeError(
        f"нет токена для {service} — выполни `yandex-mcp login` "
        f"(хранилище: {backend().describe()})")
