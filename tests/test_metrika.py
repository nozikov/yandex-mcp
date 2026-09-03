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


def test_summary_handles_empty_goal_totals(monkeypatch):
    # регрессия: reaches.get('totals', [0])[0] падал IndexError на "totals": [] у цели
    # (дефолт .get(key, default) не срабатывает, раз ключ присутствует)
    monkeypatch.setattr(metrika, "keychain_token", lambda name: "fake-token")

    def fake_http_get(url, token, params=None):
        if "goals" in url:
            return {"goals": [{"id": 1, "name": "цель без данных"}]}
        return {"totals": []}

    monkeypatch.setattr(metrika, "http_get", fake_http_get)
    text = metrika.tool_metrika_summary({"counter_id": "1"})
    assert "цель без данных (id 1): 0" in text


def test_summary_batches_goal_metrics_into_one_request(monkeypatch):
    monkeypatch.setattr(metrika, "keychain_token", lambda name: "fake-token")
    goal_requests = []

    def fake_http_get(url, token, params=None):
        if "goals" in url:
            return {"goals": [{"id": i, "name": f"цель {i}"} for i in range(1, 4)]}
        metrics = (params or {}).get("metrics", "")
        if metrics.startswith("ym:s:goal"):
            goal_requests.append(metrics)
            return {"totals": [10, 20, 30]}
        return {"totals": []}

    monkeypatch.setattr(metrika, "http_get", fake_http_get)
    text = metrika.tool_metrika_summary({"counter_id": "1"})
    assert len(goal_requests) == 1  # три цели — один запрос, не три
    assert "цель 1 (id 1): 10" in text
    assert "цель 2 (id 2): 20" in text
    assert "цель 3 (id 3): 30" in text


def test_default_previous_period_same_length_immediately_before():
    prev1, prev2 = metrika._default_previous_period("2024-01-16", "2024-01-31")
    assert prev1 == "2023-12-31"
    assert prev2 == "2024-01-15"


def test_compare_computes_delta_and_percent(monkeypatch):
    monkeypatch.setattr(metrika, "keychain_token", lambda name: "fake-token")

    def fake_http_get(url, token, params=None):
        if params.get("date1") == "2024-02-01":
            return {"totals": [200]}
        return {"totals": [100]}

    monkeypatch.setattr(metrika, "http_get", fake_http_get)
    text = metrika.tool_metrika_compare({
        "metrics": "ym:s:visits", "counter_id": "1",
        "date1": "2024-02-01", "date2": "2024-02-28",
        "prev_date1": "2024-01-01", "prev_date2": "2024-01-28",
    })
    assert "200 vs 100" in text
    assert "+100.0%" in text


def test_compare_with_dimensions_matches_rows_by_key(monkeypatch):
    monkeypatch.setattr(metrika, "keychain_token", lambda name: "fake-token")

    def fake_http_get(url, token, params=None):
        if params.get("date1") == "2024-02-01":
            return {"totals": [10], "data": [
                {"dimensions": [{"name": "google"}], "metrics": [7]},
                {"dimensions": [{"name": "direct"}], "metrics": [3]},
            ]}
        return {"totals": [5], "data": [
            {"dimensions": [{"name": "google"}], "metrics": [5]},
        ]}

    monkeypatch.setattr(metrika, "http_get", fake_http_get)
    text = metrika.tool_metrika_compare({
        "metrics": "ym:s:visits", "dimensions": "ym:s:lastsignTrafficSource", "counter_id": "1",
        "date1": "2024-02-01", "date2": "2024-02-28",
        "prev_date1": "2024-01-01", "prev_date2": "2024-01-28",
    })
    assert "google: ym:s:visits: 7 vs 5" in text
    assert "direct: ym:s:visits: 3 vs 0" in text
