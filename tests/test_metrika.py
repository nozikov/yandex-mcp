import pytest

from yandex_mcp.tools import metrika


def test_resolve_counter_uses_argument():
    assert metrika._resolve_counter({"counter_id": "123"}) == "123"


def test_resolve_counter_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(metrika, "DEFAULT_COUNTER", "456")
    assert metrika._resolve_counter({}) == "456"


def test_resolve_counter_raises_without_any_counter(monkeypatch):
    monkeypatch.setattr(metrika, "DEFAULT_COUNTER", None)
    with pytest.raises(RuntimeError):
        metrika._resolve_counter({})


def test_summary_handles_empty_totals(monkeypatch):
    # регрессия: раньше "totals": [] проходило мимо дефолта .get(key, default)
    # (он срабатывает только при отсутствующем ключе) и падало на распаковке
    monkeypatch.setattr(metrika, "keychain_token", lambda name: "fake-token")

    def fake_http_get(url, token, params=None):
        if "goals" in url:
            return {"goals": []}
        return {"totals": []}

    monkeypatch.setattr(metrika, "http_get", fake_http_get)
    text = metrika.tool_metrika_summary({"counter_id": "1"})
    assert "визиты: 0" in text
    assert "посетители: 0" in text
