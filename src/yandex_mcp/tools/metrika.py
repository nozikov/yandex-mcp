"""Инструменты Яндекс Метрики: сводка, произвольный отчёт, сравнение периодов, счётчики."""

import datetime
import os

from ..httpclient import http_get
from ..auth.tokens import service_token

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
    token = service_token("metrika")
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
    goals = goals.get("goals", [])
    # метрики целей запрашиваются пачками — иначе N целей дают N+2 последовательных
    # HTTP-запроса; Reporting API исторически ограничивает ~20 метрик за вызов
    GOAL_CHUNK = 20
    for chunk_start in range(0, len(goals), GOAL_CHUNK):
        chunk = goals[chunk_start:chunk_start + GOAL_CHUNK]
        reaches = http_get(STAT, token, {
            "ids": counter,
            "metrics": ",".join(f"ym:s:goal{goal['id']}reaches" for goal in chunk),
            "date1": date1, "date2": date2,
        })
        values = reaches.get("totals") or [0] * len(chunk)
        for goal, value in zip(chunk, values):
            lines.append(f"  {goal['name']} (id {goal['id']}): {value:.0f}")
    return "\n".join(lines)


def tool_metrika_report(arguments):
    token = service_token("metrika")
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


def _resolve_date_token(token, today):
    token = str(token)
    if token == "today":
        return today
    if token == "yesterday":
        return today - datetime.timedelta(days=1)
    if token.endswith("daysAgo"):
        return today - datetime.timedelta(days=int(token[:-len("daysAgo")]))
    return datetime.date.fromisoformat(token)


def _default_previous_period(date1, date2):
    """Период B по умолчанию: такой же длины, вплотную перед периодом A.

    Относительные токены (today/yesterday/NdaysAgo) резолвятся от локальной
    даты машины — это приближение к тому, что Метрика считает "сегодня" в
    таймзоне счётчика; для точности передавай явные date1/date2 или
    prev_date1/prev_date2 в формате YYYY-MM-DD.
    """
    today = datetime.date.today()
    start = _resolve_date_token(date1, today)
    end = _resolve_date_token(date2, today)
    length = (end - start).days
    prev_end = start - datetime.timedelta(days=1)
    prev_start = prev_end - datetime.timedelta(days=length)
    return prev_start.isoformat(), prev_end.isoformat()


def tool_metrika_compare(arguments):
    token = service_token("metrika")
    counter = _resolve_counter(arguments)
    metrics = arguments["metrics"]
    metric_names = metrics.split(",")
    dimensions = arguments.get("dimensions")
    limit = min(int(arguments.get("limit", 10)), 50)

    date1_a = arguments.get("date1", "30daysAgo")
    date2_a = arguments.get("date2", "yesterday")
    if arguments.get("prev_date1") and arguments.get("prev_date2"):
        date1_b, date2_b = arguments["prev_date1"], arguments["prev_date2"]
    else:
        date1_b, date2_b = _default_previous_period(date1_a, date2_a)

    def fetch(date1, date2):
        params = {"ids": counter, "metrics": metrics, "date1": date1, "date2": date2, "limit": limit}
        if dimensions:
            params["dimensions"] = dimensions
        if arguments.get("filters"):
            params["filters"] = arguments["filters"]
        return http_get(STAT, token, params)

    current = fetch(date1_a, date2_a)
    previous = fetch(date1_b, date2_b)

    def fmt_row(label, values_a, values_b):
        parts = []
        for name, a, b in zip(metric_names, values_a, values_b):
            delta = a - b
            pct = (delta / b * 100) if b else (100.0 if a else 0.0)
            parts.append(f"{name}: {a:g} vs {b:g} ({delta:+g}, {pct:+.1f}%)")
        return f"{label}: " + "; ".join(parts)

    lines = [f"Счётчик {counter}",
             f"период A: {date1_a} — {date2_a}",
             f"период B: {date1_b} — {date2_b}", ""]

    totals_a = current.get("totals") or [0] * len(metric_names)
    totals_b = previous.get("totals") or [0] * len(metric_names)
    lines.append(fmt_row("итого", totals_a, totals_b))

    if dimensions:
        lines.append("")
        rows_b = {tuple((d.get("name") or d.get("id")) for d in row["dimensions"]): row["metrics"]
                  for row in previous.get("data", [])}
        for row in current.get("data", []):
            key = tuple((d.get("name") or d.get("id")) for d in row["dimensions"])
            values_b = rows_b.get(key, [0] * len(metric_names))
            lines.append(fmt_row(" / ".join(key) or "—", row["metrics"], values_b))

    return "\n".join(lines)


def tool_metrika_counters(arguments):
    token = service_token("metrika")
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
        "name": "metrika_compare",
        "description": "Сравнение метрик между двумя периодами — для вопросов вроде «как изменился "
                       "трафик за последний месяц». Период B по умолчанию: такой же длины, вплотную "
                       "перед периодом A (можно задать явно через prev_date1/prev_date2). Если задан "
                       "dimensions — сравнение построчно по значениям измерения, иначе только по итогам.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "metrics": {"type": "string", "description": "через запятую, обязательно"},
                "dimensions": {"type": "string", "description": "через запятую"},
                "date1": {"type": "string", "description": "начало периода A, по умолчанию 30daysAgo"},
                "date2": {"type": "string", "description": "конец периода A, по умолчанию yesterday"},
                "prev_date1": {"type": "string", "description": "начало периода B; по умолчанию — "
                                                                 "период той же длины перед периодом A"},
                "prev_date2": {"type": "string", "description": "конец периода B"},
                "filters": {"type": "string", "description": "язык фильтров Метрики"},
                "limit": {"type": "integer", "description": "строк при сравнении по dimensions, до 50"},
                "counter_id": {"type": "string"},
            },
            "required": ["metrics"],
        },
        "handler": tool_metrika_compare,
    },
    {
        "name": "metrika_counters",
        "description": "Список доступных счётчиков Метрики с их сайтами и статусом.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_metrika_counters,
    },
]
