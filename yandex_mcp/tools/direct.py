"""Инструмент Яндекс Директа: список кампаний (только чтение)."""

from ..httpclient import http_post_json
from ..keychain import keychain_token

DIRECT = "https://api.direct.yandex.com/json/v5"


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
]
