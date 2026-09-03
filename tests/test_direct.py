from yandex_mcp.tools import direct


def test_direct_campaigns_reports_units(monkeypatch):
    monkeypatch.setattr(direct, "keychain_token", lambda name: "fake-token")

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
    monkeypatch.setattr(direct, "keychain_token", lambda name: "fake-token")

    def fake_http_post_json(url, token, payload, bearer=True, headers_out=None):
        return {"error": {"error_code": 58, "error_string": "no access",
                          "error_detail": "заявка не одобрена"}}

    monkeypatch.setattr(direct, "http_post_json", fake_http_post_json)
    text = direct.tool_direct_campaigns({})
    assert "код 58" in text
