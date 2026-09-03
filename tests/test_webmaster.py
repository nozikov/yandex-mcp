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
