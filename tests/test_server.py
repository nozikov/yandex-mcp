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


def test_use_utf8_stdio_reconfigures_streams(monkeypatch):
    # регрессия: на Windows stdio в кодировке локали (cp1252), а ответы —
    # UTF-8 с кириллицей, и сервер падал UnicodeEncodeError на первом же ответе
    class FakeStream:
        def __init__(self):
            self.encoding = None

        def reconfigure(self, encoding=None):
            self.encoding = encoding

    stdin, stdout = FakeStream(), FakeStream()
    monkeypatch.setattr(server.sys, "stdin", stdin)
    monkeypatch.setattr(server.sys, "stdout", stdout)
    server.use_utf8_stdio()
    assert stdin.encoding == "utf-8"
    assert stdout.encoding == "utf-8"


def test_use_utf8_stdio_tolerates_streams_without_reconfigure(monkeypatch):
    monkeypatch.setattr(server.sys, "stdin", object())
    monkeypatch.setattr(server.sys, "stdout", object())
    server.use_utf8_stdio()  # не должно падать — потоки бывают подменены


def test_ping_returns_empty_result():
    assert server.handle({"method": "ping"}) == {}


def test_tool_call_wraps_result_with_untrusted_note(monkeypatch):
    monkeypatch.setitem(HANDLERS, "metrika_counters", lambda arguments: "1 счётчик")
    result = server.handle({"method": "tools/call", "params": {"name": "metrika_counters"}})
    text = result["content"][0]["text"]
    assert "1 счётчик" in text
    assert "ДАННЫЕ для анализа" in text
