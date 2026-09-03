from yandex_mcp.tools import webmaster
from yandex_mcp.tools.webmaster import _host_matches


def make_host(url):
    return {"ascii_host_url": url, "unicode_host_url": url}


def test_exact_domain_matches():
    host = make_host("http://example.com/")
    assert _host_matches("http://example.com/page", host) is True


def test_superstring_domain_does_not_match():
    # регрессия: раньше матчинг шёл строковым startswith(), и
    # example.com.br ошибочно попадал под хост example.com
    host = make_host("http://example.com/")
    assert _host_matches("http://example.com.br/page", host) is False


def test_different_scheme_still_matches_by_netloc():
    host = make_host("http://example.com/")
    assert _host_matches("https://example.com/page", host) is True


def test_unrelated_host_does_not_match():
    host = make_host("http://example.com/")
    assert _host_matches("http://other.com/page", host) is False


def _fake_host_lookup(url):
    if url.endswith("/user"):
        return {"user_id": 1}
    if url.endswith("/hosts"):
        return {"hosts": [{"host_id": "h1", "ascii_host_url": "http://example.com/"}]}
    return None


def test_indexing_reports_history_by_date(monkeypatch):
    monkeypatch.setattr(webmaster, "service_token", lambda name: "fake-token")

    def fake_http_get(url, token, params=None):
        found = _fake_host_lookup(url)
        if found is not None:
            return found
        if url.endswith("/search-urls/in-search/history"):
            return {"history": [{"date": "2024-01-01T00:00:00Z", "value": 100},
                                {"date": "2024-01-02T00:00:00Z", "value": 120}]}
        raise AssertionError(url)

    monkeypatch.setattr(webmaster, "http_get", fake_http_get)
    text = webmaster.tool_webmaster_indexing({})
    assert "2024-01-01: 100" in text
    assert "2024-01-02: 120" in text


def test_sitemaps_reports_list(monkeypatch):
    monkeypatch.setattr(webmaster, "service_token", lambda name: "fake-token")

    def fake_http_get(url, token, params=None):
        found = _fake_host_lookup(url)
        if found is not None:
            return found
        if url.endswith("/sitemaps"):
            return {"sitemaps": [{"sitemap_url": "http://example.com/sitemap.xml",
                                  "urls_count": 42, "errors_count": 0,
                                  "last_access_date": "2024-01-05T00:00:00Z"}]}
        raise AssertionError(url)

    monkeypatch.setattr(webmaster, "http_get", fake_http_get)
    text = webmaster.tool_webmaster_sitemaps({})
    assert "sitemap.xml" in text
    assert "42 url" in text
