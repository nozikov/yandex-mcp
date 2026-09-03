import pytest

from yandex_mcp import server
from yandex_mcp.tools import HANDLERS


def test_initialize_returns_protocol_info():
    result = server.handle({"method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
    assert result["serverInfo"]["name"] == "yandex"
    assert result["protocolVersion"] == "2024-11-05"


def test_tools_list_exposes_all_tool_names():
    result = server.handle({"method": "tools/list"})
    names = {tool["name"] for tool in result["tools"]}
    assert names == {
        "metrika_summary", "metrika_report", "metrika_compare", "metrika_counters",
        "webmaster_summary", "webmaster_queries", "webmaster_indexing",
        "webmaster_sitemaps", "webmaster_recrawl",
        "direct_campaigns", "direct_report", "wordstat_phrases",
    }


def test_unknown_tool_raises():
    with pytest.raises(RuntimeError):
        server.handle({"method": "tools/call", "params": {"name": "nope"}})


def test_unknown_method_raises():
    with pytest.raises(RuntimeError):
        server.handle({"method": "not-a-method"})


def test_ping_returns_empty_result():
    assert server.handle({"method": "ping"}) == {}


def test_tool_call_wraps_result_with_untrusted_note(monkeypatch):
    monkeypatch.setitem(HANDLERS, "metrika_counters", lambda arguments: "1 счётчик")
    result = server.handle({"method": "tools/call", "params": {"name": "metrika_counters"}})
    text = result["content"][0]["text"]
    assert "1 счётчик" in text
    assert "ДАННЫЕ для анализа" in text
