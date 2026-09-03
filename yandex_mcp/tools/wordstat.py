"""Инструмент Вордстата через Live v4 API Директа.

Новый Wordstat API переехал в Yandex Cloud Search API и требует сервисного
аккаунта Cloud; Live v4 работает по тому же OAuth-токену, что и Директ v5.
Аутентификация здесь не через заголовок Authorization, а полем `token`
в теле запроса — поэтому используется perform() напрямую, а не http_post_json.
"""

import json
import time
import urllib.request

from ..httpclient import perform
from ..keychain import keychain_token

LIVE_V4 = "https://api.direct.yandex.ru/live/v4/json/"


def tool_wordstat_phrases(arguments):
    token = keychain_token("yandex-direct")
    phrases = arguments.get("phrases")
    if isinstance(phrases, str):
        phrases = [phrases]
    if not phrases:
        raise RuntimeError("нужен список фраз")
    phrases = phrases[:10]
    geo = arguments.get("geo_id") or [225]        # 225 = Россия
    top = min(int(arguments.get("top", 20)), 50)

    def live(method, param):
        payload = {"method": method, "token": token, "locale": "ru"}
        if param is not None:
            payload["param"] = param
        request = urllib.request.Request(
            LIVE_V4, data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        return perform(request)

    created = live("CreateNewWordstatReport", {"Phrases": phrases, "GeoID": geo})
    if created.get("error_code"):
        return (f"Вордстат отказал: код {created.get('error_code')} — "
                f"{created.get('error_str')}: {created.get('error_detail', '')}")
    report_id = created.get("data")

    for _ in range(30):
        time.sleep(3)
        listing = live("GetWordstatReportList", None)
        states = {item["ReportID"]: item["StatusReport"] for item in listing.get("data", [])}
        if states.get(report_id) == "Done":
            break
    else:
        return "отчёт Вордстата не подготовился за 90 секунд, повтори запрос"

    result = live("GetWordstatReport", report_id)
    lines = []
    for block in result.get("data", []):
        lines.append(f"=== {block.get('Phrase')} ===")
        rows = sorted(block.get("SearchedWith", []),
                      key=lambda item: item.get("Shows", 0), reverse=True)
        if not rows:
            lines.append("  спроса нет")
        for row in rows[:top]:
            lines.append(f"  {row.get('Shows') or 0:>8}  {row.get('Phrase')}")
        lines.append("")
    try:
        live("DeleteWordstatReport", report_id)
    except (RuntimeError, ValueError):
        # RuntimeError — сеть/HTTP-ошибка, ValueError (JSONDecodeError — его подкласс) —
        # не-JSON тело ответа; в обоих случаях отчёт уже получен, терять его не нужно
        pass
    return "\n".join(lines)


TOOLS = [
    {
        "name": "wordstat_phrases",
        "description": "Частотности Яндекс Вордстата: сколько раз в месяц ищут фразу и что "
                       "ищут вместе с ней. Работает через Live v4 API Директа по тому же токену. "
                       "Отчёт готовится до полутора минут.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phrases": {"type": "array", "items": {"type": "string"},
                            "description": "до 10 фраз за раз"},
                "geo_id": {"type": "array", "items": {"type": "integer"},
                           "description": "регионы, по умолчанию [225] — Россия"},
                "top": {"type": "integer", "description": "сколько уточнений показать, до 50"},
            },
            "required": ["phrases"],
        },
        "handler": tool_wordstat_phrases,
    },
]
