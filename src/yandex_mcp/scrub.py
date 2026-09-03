"""Вычищение секретов из текста перед тем, как он уйдёт в ответ или в ошибку."""

import re

SECRET_PATTERNS = [
    re.compile(r"(?i)\b(OAuth|Bearer)\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\by[0-3]_[A-Za-z0-9._-]{20,}"),
]


def scrub(text):
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("***", text)
    return text
