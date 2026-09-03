from yandex_mcp.scrub import scrub


def test_scrubs_oauth_bearer_header():
    text = "Authorization: OAuth AQAAAAA1234567890abc failed"
    scrubbed = scrub(text)
    assert "AQAAAAA1234567890abc" not in scrubbed
    assert "***" in scrubbed


def test_scrubs_yandex_token_literal():
    token = "y0_" + "A" * 25
    text = f"token={token} expired"
    scrubbed = scrub(text)
    assert token not in scrubbed


def test_leaves_unrelated_text_untouched():
    text = "визиты: 42, отказы: 30.5%"
    assert scrub(text) == text
