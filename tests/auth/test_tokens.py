import pytest

from yandex_mcp.auth import store, tokens


@pytest.fixture(autouse=True)
def _isolated(file_store):
    """Все тесты модуля работают на временном файловом хранилище."""


def test_service_token_prefers_dedicated_token():
    store.set_secret("yandex-metrika-token", "узкий")
    store.set_secret(tokens.UNIFIED_TOKEN, "общий")
    assert tokens.service_token("yandex-metrika") == "узкий"


def test_service_token_falls_back_to_unified_login():
    store.set_secret(tokens.UNIFIED_TOKEN, "общий")
    assert tokens.service_token("yandex-metrika") == "общий"


def test_service_token_error_mentions_login_and_storage():
    with pytest.raises(RuntimeError) as excinfo:
        tokens.service_token("yandex-metrika")
    message = str(excinfo.value)
    assert "yandex-mcp login" in message
    assert "хранилище" in message
