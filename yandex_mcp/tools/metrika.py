"""Инструменты Яндекс Метрики: сводка, произвольный отчёт, список счётчиков."""

import os

from ..httpclient import http_get
from ..keychain import keychain_token

STAT = "https://api-metrika.yandex.net/stat/v1/data"
MANAGEMENT = "https://api-metrika.yandex.net/management/v1"

# необязательный дефолт, чтобы не передавать counter_id в каждом вызове —
# задаётся в конфиге MCP-клиента (env), в коде ничего не зашито
DEFAULT_COUNTER = os.environ.get("YANDEX_MCP_DEFAULT_COUNTER")


def _resolve_counter(arguments):
    counter = arguments.get("counter_id") or DEFAULT_COUNTER
    if not counter:
        raise RuntimeError(
            "не передан counter_id и не задан YANDEX_MCP_DEFAULT_COUNTER — "
            "укажи ID счётчика Метрики")
    return str(counter)


def tool_metrika_summary(arguments):
    token = keychain_token("yandex-metrika")
    counter = _resolve_counter(arguments)
    date1 = arguments.get("date1", "30daysAgo")
    date2 = arguments.get("date2", "yesterday")

    totals = http_get(STAT, token, {
        "ids": counter,
        "metrics": "ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:avgVisitDurationSeconds,ym:s:pageDepth",
        "date1": date1, "date2": date2,
    })
    goals = http_get(f"{MANAGEMENT}/counter/{counter}/goals", token)

    lines = [f"Счётчик {counter}, период {date1} — {date2}", ""]
    visits, users, bounce, duration, depth = totals.get("totals") or [0] * 5
    lines += [
        f"визиты: {visits:.0f}",
        f"посетители: {users:.0f}",
        f"отказы: {bounce:.1f}%",
        f"средний визит: {duration / 60:.1f} мин",
        f"глубина: {depth:.1f} страниц",
        "",
        "Цели:",
    ]
    for goal in goals.get("goals", []):
        reaches = http_get(STAT, token, {
            "ids": counter, "metrics": f"ym:s:goal{goal['id']}reaches",
            "date1": date1, "date2": date2,
        })
        lines.append(f"  {goal['name']} (id {goal['id']}): {reaches.get('totals', [0])[0]:.0f}")
    return "\n".join(lines)


def tool_metrika_report(arguments):
    token = keychain_token("yandex-metrika")
    params = {
        "ids": _resolve_counter(arguments),
        "metrics": arguments["metrics"],
        "date1": arguments.get("date1", "30daysAgo"),
        "date2": arguments.get("date2", "yesterday"),
        "limit": min(int(arguments.get("limit", 20)), 200),
    }
    for optional in ("dimensions", "filters", "sort"):
        if arguments.get(optional):
            params[optional] = arguments[optional]

    result = http_get(STAT, token, params)
    header = f"metrics={params['metrics']} dimensions={params.get('dimensions', '—')}"
    lines = [header, ""]

    for row in result.get("data", []):
        names = " / ".join((d.get("name") or d.get("id") or "—") for d in row["dimensions"])
        values = "  ".join(f"{value:g}" for value in row["metrics"])
        lines.append(f"{names or 'итого'}: {values}")

    if result.get("totals"):
        lines.append("")
        lines.append("итого: " + "  ".join(f"{value:g}" for value in result["totals"]))
    return "\n".join(lines) if len(lines) > 2 else "данных нет"


def tool_metrika_counters(arguments):
    token = keychain_token("yandex-metrika")
    result = http_get(f"{MANAGEMENT}/counters", token)
    lines = []
    for counter in result.get("counters", []):
        lines.append(f"{counter.get('id')}  {counter.get('name')}  "
                     f"[{counter.get('site')}]  {counter.get('status')}")
    return "\n".join(lines) or "счётчиков нет"


TOOLS = [
    {
        "name": "metrika_summary",
        "description": "Сводка Яндекс Метрики за период: визиты, посетители, отказы, "
                       "длительность, глубина и достижения всех целей счётчика.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "counter_id": {"type": "string",
                               "description": "ID счётчика Метрики; если не передан, берётся "
                                              "из YANDEX_MCP_DEFAULT_COUNTER"},
                "date1": {"type": "string", "description": "начало: YYYY-MM-DD или 30daysAgo"},
                "date2": {"type": "string", "description": "конец: YYYY-MM-DD или yesterday"},
            },
        },
        "handler": tool_metrika_summary,
    },
    {
        "name": "metrika_report",
        "description": "Произвольный отчёт Reporting API Метрики. Метрики: ym:s:visits, ym:s:users, "
                       "ym:s:bounceRate, ym:s:goal<ID>reaches, ym:s:goal<ID>conversionRate, "
                       "ym:pv:pageviews. Измерения: ym:s:lastsignTrafficSource, ym:s:lastsignSourceEngine, "
                       "ym:s:searchPhrase, ym:s:startURLPath, ym:pv:URLPath, ym:s:regionCity, "
                       "ym:s:deviceCategory, ym:s:UTMSource, ym:s:UTMCampaign, ym:s:date, ym:s:referalSource. "
                       "ID целей смотри через metrika_summary — там они перечислены с достижениями.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "metrics": {"type": "string", "description": "через запятую, обязательно"},
                "dimensions": {"type": "string", "description": "через запятую"},
                "date1": {"type": "string"},
                "date2": {"type": "string"},
                "filters": {"type": "string", "description": "язык фильтров Метрики"},
                "sort": {"type": "string"},
                "limit": {"type": "integer", "description": "до 200"},
                "counter_id": {"type": "string"},
            },
            "required": ["metrics"],
        },
        "handler": tool_metrika_report,
    },
    {
        "name": "metrika_counters",
        "description": "Список доступных счётчиков Метрики с их сайтами и статусом.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_metrika_counters,
    },
]
