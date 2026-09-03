from yandex_mcp.tools import direct


def test_direct_campaigns_reports_units(monkeypatch):
    monkeypatch.setattr(direct, "service_token", lambda name: "fake-token")

    def fake_http_post_json(url, token, payload, bearer=True, headers_out=None):
        if headers_out is not None:
            headers_out["Units"] = "10/990/1000"
        return {"result": {"Campaigns": [
            {"Id": 1, "Name": "Test", "State": "ON", "Status": "ACCEPTED"},
        ]}}

    monkeypatch.setattr(direct, "http_post_json", fake_http_post_json)
    text = direct.tool_direct_campaigns({})
    assert "кампаний: 1" in text
    assert "остаток 990 из суточных 1000" in text


def test_direct_campaigns_surfaces_api_error(monkeypatch):
    monkeypatch.setattr(direct, "service_token", lambda name: "fake-token")

    def fake_http_post_json(url, token, payload, bearer=True, headers_out=None):
        return {"error": {"error_code": 58, "error_string": "no access",
                          "error_detail": "заявка не одобрена"}}

    monkeypatch.setattr(direct, "http_post_json", fake_http_post_json)
    text = direct.tool_direct_campaigns({})
    assert "код 58" in text


def test_build_report_payload_defaults():
    payload, field_names = direct._build_report_payload({})
    assert payload["DateRangeType"] == "LAST_30_DAYS"
    assert payload["ReportType"] == "CAMPAIGN_PERFORMANCE_REPORT"
    assert field_names == direct.DEFAULT_REPORT_FIELDS
    assert "Filter" not in payload["SelectionCriteria"]


def test_build_report_payload_custom_dates_fields_and_campaigns():
    payload, field_names = direct._build_report_payload({
        "date1": "2024-01-01", "date2": "2024-01-31",
        "fields": "CampaignId,Cost",
        "campaign_ids": [111, 222],
    })
    assert payload["DateRangeType"] == "CUSTOM_DATE"
    assert payload["SelectionCriteria"]["DateFrom"] == "2024-01-01"
    assert payload["SelectionCriteria"]["DateTo"] == "2024-01-31"
    assert field_names == ["CampaignId", "Cost"]
    assert payload["SelectionCriteria"]["Filter"][0]["Values"] == ["111", "222"]


def test_format_report_renders_tsv_rows():
    text = direct._format_report("123\tTest\t10\n456\tOther\t20\n",
                                  ["CampaignId", "CampaignName", "Clicks"])
    assert "Test" in text
    assert "20" in text


def test_format_report_empty_body():
    assert direct._format_report("", ["CampaignId"]) == "данных нет"


def test_report_polls_until_ready(monkeypatch):
    # Reports API отвечает 201/202, пока отчёт не готов, тул должен сам поллить
    monkeypatch.setattr(direct, "service_token", lambda name: "fake-token")
    monkeypatch.setattr(direct.time, "sleep", lambda seconds: None)

    calls = {"n": 0}

    def fake_do_request(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return 202, "", "1"
        return 200, "1\tCamp\t10\t5\t100.5\n", None

    monkeypatch.setattr(direct, "_do_report_request", fake_do_request)
    text = direct.tool_direct_report({})
    assert calls["n"] == 3
    assert "Camp" in text


def test_report_raises_on_unexpected_status(monkeypatch):
    monkeypatch.setattr(direct, "service_token", lambda name: "fake-token")
    monkeypatch.setattr(direct, "_do_report_request", lambda request: (500, "", None))

    import pytest
    with pytest.raises(RuntimeError):
        direct.tool_direct_report({})
