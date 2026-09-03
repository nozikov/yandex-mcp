"""Инструменты Яндекс Директа: список кампаний и отчёты по расходу/эффективности.

direct_report использует Reports API v5 (POST /json/v5/reports), отдельный от
остального Директа сервис с асинхронной генерацией отчётов: см.
https://yandex.com/dev/direct/doc/ru/reports и https://yandex.ru/dev/direct/doc/ru/headers.
Заголовки processingMode/skipReportHeader/skipReportSummary/returnMoneyInMicros и
статусы 200 (готово) / 201, 202 (в очереди, повторить через retryIn секунд) —
поэтому это не http_post_json, а отдельный низкоуровневый запрос с чтением
заголовков ответа и телом в TSV, а не в JSON.
"""

import json
import time
import urllib.error
import urllib.request

from ..httpclient import http_post_json
from ..keychain import keychain_token
from ..scrub import scrub

DIRECT = "https://api.direct.yandex.com/json/v5"
REPORTS = "https://api.direct.yandex.com/json/v5/reports"

DEFAULT_REPORT_FIELDS = ["CampaignId", "CampaignName", "Impressions", "Clicks", "Cost", "Ctr", "AvgCpc"]


def tool_direct_campaigns(arguments):
    token = keychain_token("yandex-direct")
    response_headers = {}
    result = http_post_json(f"{DIRECT}/campaigns", token, headers_out=response_headers, payload={
        "method": "get",
        "params": {
            "SelectionCriteria": {},
            "FieldNames": ["Id", "Name", "State", "Status", "DailyBudget"],
            "Page": {"Limit": min(int(arguments.get("limit", 50)), 200)},
        },
    })
    if "error" in result:
        error = result["error"]
        return (f"Директ отказал: код {error.get('error_code')} — "
                f"{error.get('error_string')}: {error.get('error_detail')}")

    campaigns = result.get("result", {}).get("Campaigns", [])
    if not campaigns:
        return "кампаний нет"
    lines = [f"кампаний: {len(campaigns)}"]
    for campaign in campaigns:
        lines.append(f"  {campaign.get('Id')}  {campaign.get('Name')}  "
                     f"{campaign.get('State')}/{campaign.get('Status')}")
    # Директ отдаёт расход баллов заголовком Units: <потрачено>/<остаток>/<суточный лимит>
    units = response_headers.get("Units")
    if units:
        parts = units.split("/")
        if len(parts) == 3:
            lines.append(f"баллы API: потрачено на запрос {parts[0]}, "
                         f"остаток {parts[1]} из суточных {parts[2]}")
        else:
            lines.append(f"баллы API: {units}")
    return "\n".join(lines)


def _do_report_request(request):
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            retry_in = response.headers.get("retryIn")
            return response.status, response.read().decode("utf-8", errors="replace"), retry_in
    except urllib.error.HTTPError as error:
        detail = scrub(error.read().decode(errors="replace")[:600])
        raise RuntimeError(f"Reports API вернул HTTP {error.code}: {detail}")
    except urllib.error.URLError as error:
        raise RuntimeError(f"сеть недоступна: {error.reason}")


def _build_report_payload(arguments):
    field_names = ([f.strip() for f in arguments["fields"].split(",")] if arguments.get("fields")
                   else list(DEFAULT_REPORT_FIELDS))

    selection = {}
    if arguments.get("campaign_ids"):
        selection["Filter"] = [{
            "Field": "CampaignId",
            "Operator": "IN",
            "Values": [str(c) for c in arguments["campaign_ids"]],
        }]

    date1, date2 = arguments.get("date1"), arguments.get("date2")
    if date1 or date2:
        date_range_type = "CUSTOM_DATE"
        selection["DateFrom"] = date1 or date2
        selection["DateTo"] = date2 or date1
    else:
        date_range_type = arguments.get("date_range", "LAST_30_DAYS")

    report_type = arguments.get("report_type", "CAMPAIGN_PERFORMANCE_REPORT")
    payload = {
        "SelectionCriteria": selection,
        "FieldNames": field_names,
        "ReportName": f"mcp-{report_type}-{int(time.time() * 1000)}",
        "ReportType": report_type,
        "DateRangeType": date_range_type,
        "Format": "TSV",
        "IncludeVAT": "NO",
        "IncludeDiscount": "NO",
    }
    return payload, field_names


def _format_report(body, field_names):
    rows = [line.split("\t") for line in body.strip("\n").splitlines() if line.strip()]
    if not rows:
        return "данных нет"
    lines = [f"поля: {', '.join(field_names)}", ""]
    for row in rows:
        lines.append("  " + "  ".join(row))
    return "\n".join(lines)


def tool_direct_report(arguments):
    token = keychain_token("yandex-direct")
    payload, field_names = _build_report_payload(arguments)
    body_bytes = json.dumps({"params": payload}, ensure_ascii=False).encode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "processingMode": "auto",
        "returnMoneyInMicros": "false",
        "skipReportHeader": "true",
        "skipReportSummary": "true",
        "skipColumnHeader": "true",
        "Content-Type": "application/json; charset=utf-8",
    }
    if arguments.get("client_login"):
        headers["Client-Login"] = arguments["client_login"]

    for _ in range(20):
        request = urllib.request.Request(REPORTS, data=body_bytes, headers=headers, method="POST")
        status, body, retry_in = _do_report_request(request)
        if status == 200:
            return _format_report(body, field_names)
        if status in (201, 202):
            time.sleep(min(int(retry_in or 10), 30))
            continue
        raise RuntimeError(f"Reports API вернул неожиданный статус {status}")
    return "отчёт Директа не подготовился за отведённое время, повтори запрос"


TOOLS = [
    {
        "name": "direct_campaigns",
        "description": "Список кампаний Яндекс Директа (только чтение) и остаток баллов API. "
                       "Пока не подана заявка на доступ к API Директа, вернёт код 58.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
        },
        "handler": tool_direct_campaigns,
    },
    {
        "name": "direct_report",
        "description": "Отчёт по расходу/показам/кликам Директа (Reports API v5) — то, чего нет в "
                       "direct_campaigns: реальные цифры эффективности по кампаниям, объявлениям, "
                       "группам или поисковым запросам. Период — либо готовый диапазон Директа "
                       "(date_range, по умолчанию LAST_30_DAYS: LAST_7_DAYS, THIS_MONTH, ALL_TIME и т.д.), "
                       "либо явные date1/date2 в формате YYYY-MM-DD (относительные вроде 30daysAgo, "
                       "как в Метрике, не поддерживаются). Отчёт может готовиться асинхронно — "
                       "тул сам ждёт и повторяет запрос, суммарно до нескольких минут.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "report_type": {"type": "string",
                                "description": "по умолчанию CAMPAIGN_PERFORMANCE_REPORT; другие: "
                                               "ADGROUP_PERFORMANCE_REPORT, AD_PERFORMANCE_REPORT, "
                                               "SEARCH_QUERY_PERFORMANCE_REPORT"},
                "fields": {"type": "string",
                          "description": "через запятую, по умолчанию CampaignId,CampaignName,"
                                         "Impressions,Clicks,Cost,Ctr,AvgCpc"},
                "date_range": {"type": "string", "description": "готовый диапазон Директа, "
                                                                 "по умолчанию LAST_30_DAYS"},
                "date1": {"type": "string", "description": "YYYY-MM-DD — задаёт CUSTOM_DATE"},
                "date2": {"type": "string", "description": "YYYY-MM-DD"},
                "campaign_ids": {"type": "array", "items": {"type": "integer"},
                                 "description": "фильтр по ID кампаний"},
                "client_login": {"type": "string",
                                 "description": "логин клиента для агентских аккаунтов, опционально"},
            },
        },
        "handler": tool_direct_report,
    },
]
