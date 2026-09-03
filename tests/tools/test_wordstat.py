import json

import pytest

from yandex_mcp.tools import wordstat


def test_keeps_report_when_cleanup_fails(monkeypatch):
    # регрессия: раньше исключение из финального DeleteWordstatReport
    # выбрасывалось наружу и терялся уже готовый отчёт
    monkeypatch.setattr(wordstat, "service_token", lambda name: "fake-token")
    monkeypatch.setattr(wordstat.time, "sleep", lambda seconds: None)

    def fake_perform(request):
        payload = json.loads(request.data)
        method = payload["method"]
        if method == "CreateNewWordstatReport":
            return {"data": "report-1"}
        if method == "GetWordstatReportList":
            return {"data": [{"ReportID": "report-1", "StatusReport": "Done"}]}
        if method == "GetWordstatReport":
            return {"data": [{"Phrase": "test", "SearchedWith":
                              [{"Shows": 100, "Phrase": "test query"}]}]}
        if method == "DeleteWordstatReport":
            raise RuntimeError("API вернул HTTP 500: временная ошибка")
        raise AssertionError(f"неожиданный метод {method}")

    monkeypatch.setattr(wordstat, "perform", fake_perform)
    text = wordstat.tool_wordstat_phrases({"phrases": ["test"]})
    assert "test query" in text
    assert "100" in text


def test_requires_phrases(monkeypatch):
    monkeypatch.setattr(wordstat, "service_token", lambda name: "fake-token")
    with pytest.raises(RuntimeError):
        wordstat.tool_wordstat_phrases({})


def test_keeps_report_when_cleanup_raises_non_json_response(monkeypatch):
    # регрессия: try/except вокруг DeleteWordstatReport ловил только RuntimeError,
    # а perform() на не-JSON теле ответа кидает json.JSONDecodeError (подкласс ValueError)
    monkeypatch.setattr(wordstat, "service_token", lambda name: "fake-token")
    monkeypatch.setattr(wordstat.time, "sleep", lambda seconds: None)

    def fake_perform(request):
        payload = json.loads(request.data)
        method = payload["method"]
        if method == "CreateNewWordstatReport":
            return {"data": "report-1"}
        if method == "GetWordstatReportList":
            return {"data": [{"ReportID": "report-1", "StatusReport": "Done"}]}
        if method == "GetWordstatReport":
            return {"data": [{"Phrase": "test", "SearchedWith":
                              [{"Shows": 100, "Phrase": "test query"}]}]}
        if method == "DeleteWordstatReport":
            json.loads("не json")  # имитирует json.JSONDecodeError внутри perform()
        raise AssertionError(f"неожиданный метод {method}")

    monkeypatch.setattr(wordstat, "perform", fake_perform)
    text = wordstat.tool_wordstat_phrases({"phrases": ["test"]})
    assert "test query" in text


def test_handles_row_without_shows(monkeypatch):
    # регрессия: f"{row.get('Shows'):>8}" падал TypeError, если у уточнения нет Shows
    monkeypatch.setattr(wordstat, "service_token", lambda name: "fake-token")
    monkeypatch.setattr(wordstat.time, "sleep", lambda seconds: None)

    def fake_perform(request):
        payload = json.loads(request.data)
        method = payload["method"]
        if method == "CreateNewWordstatReport":
            return {"data": "report-1"}
        if method == "GetWordstatReportList":
            return {"data": [{"ReportID": "report-1", "StatusReport": "Done"}]}
        if method == "GetWordstatReport":
            return {"data": [{"Phrase": "test", "SearchedWith":
                              [{"Phrase": "без показов"}]}]}
        if method == "DeleteWordstatReport":
            return {}
        raise AssertionError(f"неожиданный метод {method}")

    monkeypatch.setattr(wordstat, "perform", fake_perform)
    text = wordstat.tool_wordstat_phrases({"phrases": ["test"]})
    assert "без показов" in text
