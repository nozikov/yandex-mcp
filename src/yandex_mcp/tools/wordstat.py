"""Инструмент Вордстата через Live v4 API Директа.

Новый Wordstat API переехал в Yandex Cloud Search API и требует сервисного
аккаунта Cloud; Live v4 работает по тому же OAuth-токену, что и Директ v5.
Аутентификация здесь не через заголовок Authorization, а полем `token`
в теле запроса — поэтому используется perform() напрямую, а не http_post_json.

Отчёт готовится на стороне Яндекса около трёх минут, а очередь ограничена
несколькими отчётами на аккаунт. Поэтому вызов сначала ищет готовый отчёт
с прошлой попытки и только потом заказывает новый, а по таймауту отчёт
намеренно НЕ удаляется — следующий такой же вызов заберёт его почти мгновенно.
"""

import json
import os
import time
import urllib.request

from ..httpclient import perform
from ..auth.tokens import service_token

LIVE_V4 = "https://api.direct.yandex.ru/live/v4/json/"

# сколько ждать готовности в одном вызове: меньше типичных трёх минут,
# чтобы не упереться в таймаут MCP-клиента — остаток добирается повторным вызовом
WAIT_SECONDS = int(os.environ.get("YANDEX_MCP_WORDSTAT_WAIT", "170"))
POLL_SECONDS = 5
MAX_POLLS = 60


def _normalize(phrases):
    if isinstance(phrases, str):
        phrases = [phrases]
    if not phrases:
        raise RuntimeError("нужен список фраз")
    return list(phrases)[:10]


def _key(phrases):
    return [str(phrase).strip().lower() for phrase in phrases]


def _format(blocks, top):
    lines = []
    for block in blocks:
        lines.append(f"=== {block.get('Phrase')} ===")
        rows = sorted(block.get("SearchedWith", []),
                      key=lambda item: item.get("Shows", 0), reverse=True)
        if not rows:
            lines.append("  спроса нет")
        for row in rows[:top]:
            lines.append(f"  {row.get('Shows') or 0:>8}  {row.get('Phrase')}")
        lines.append("")
    return "\n".join(lines)


def _drop(live, report_id):
    try:
        live("DeleteWordstatReport", report_id)
    except (RuntimeError, ValueError):
        # RuntimeError — сеть/HTTP-ошибка, ValueError (JSONDecodeError — его подкласс) —
        # не-JSON тело ответа; в обоих случаях отчёт уже получен, терять его не нужно
        pass


def _take_ready(live, wanted, top):
    """Забрать готовый отчёт с прошлого вызова, если он про те же фразы.

    Чужие отчёты не трогаем: набор фраз не совпал — значит его заказал не этот
    инструмент, и удалять его нельзя.
    """
    for item in live("GetWordstatReportList").get("data", []):
        if item.get("StatusReport") != "Done":
            continue
        blocks = (live("GetWordstatReport", item["ReportID"]) or {}).get("data") or []
        if _key(block.get("Phrase") for block in blocks) != wanted:
            continue
        text = _format(blocks, top)
        _drop(live, item["ReportID"])
        return text
    return None


def tool_wordstat_phrases(arguments):
    phrases = _normalize(arguments.get("phrases"))
    token = service_token("direct")
    geo = arguments.get("geo_id") or [225]        # 225 = Россия
    top = min(int(arguments.get("top", 20)), 50)

    def live(method, param=None):
        payload = {"method": method, "token": token, "locale": "ru"}
        if param is not None:
            payload["param"] = param
        request = urllib.request.Request(
            LIVE_V4, data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        return perform(request)

    wanted = _key(phrases)
    ready = _take_ready(live, wanted, top)
    if ready is not None:
        return ready

    created = live("CreateNewWordstatReport", {"Phrases": phrases, "GeoID": geo})
    if created.get("error_code"):
        hint = ""
        if str(created.get("error_code")) == "31":
            hint = ("\nОчередь отчётов Вордстата переполнена — в ней лежат отчёты, "
                    "заказанные не этим инструментом. Удалить их можно в Директе.")
        return (f"Вордстат отказал: код {created.get('error_code')} — "
                f"{created.get('error_str')}: {created.get('error_detail', '')}{hint}")
    report_id = created.get("data")

    deadline = time.monotonic() + WAIT_SECONDS
    done = False
    for _ in range(MAX_POLLS):
        time.sleep(POLL_SECONDS)
        listing = live("GetWordstatReportList")
        states = {item["ReportID"]: item["StatusReport"] for item in listing.get("data", [])}
        if states.get(report_id) == "Done":
            done = True
            break
        if time.monotonic() > deadline:
            break

    if not done:
        # отчёт намеренно остаётся в очереди: повторный вызов заберёт его через _take_ready
        return ("Отчёт Вордстата ещё готовится — у Яндекса это занимает около трёх минут. "
                "Повтори этот же вызов через минуту: готовый отчёт подхватится сразу, "
                "заново заказывать не будет.")

    blocks = (live("GetWordstatReport", report_id) or {}).get("data") or []
    text = _format(blocks, top)
    _drop(live, report_id)
    return text


TOOLS = [
    {
        "name": "wordstat_phrases",
        "description": "Частотности Яндекс Вордстата: сколько раз в месяц ищут фразу и что "
                       "ищут вместе с ней. Работает через Live v4 API Директа по тому же токену. "
                       "Отчёт готовится у Яндекса около трёх минут; если вызов вернул «ещё "
                       "готовится» — повтори его с теми же фразами, результат подхватится.",
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
