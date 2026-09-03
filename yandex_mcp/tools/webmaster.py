"""Инструменты Яндекс Вебмастера: сводка, поисковые запросы, переобход."""

import urllib.parse

from ..httpclient import http_get, http_post_json
from ..keychain import keychain_token

WEBMASTER = "https://api.webmaster.yandex.net/v4"


def _webmaster_host(token):
    user_id = http_get(f"{WEBMASTER}/user", token)["user_id"]
    hosts = http_get(f"{WEBMASTER}/user/{user_id}/hosts", token).get("hosts", [])
    if not hosts:
        raise RuntimeError("в Вебмастере нет подтверждённых сайтов")
    return user_id, hosts


def _host_matches(url, host):
    netloc = urllib.parse.urlsplit(url).netloc.lower()
    for key in ("unicode_host_url", "ascii_host_url"):
        candidate = host.get(key)
        if candidate and urllib.parse.urlsplit(candidate).netloc.lower() == netloc:
            return True
    return False


def tool_webmaster_summary(arguments):
    token = keychain_token("yandex-webmaster")
    user_id, hosts = _webmaster_host(token)
    lines = []
    for host in hosts:
        host_id = host["host_id"]
        summary = http_get(f"{WEBMASTER}/user/{user_id}/hosts/{host_id}/summary", token)
        diagnostics = http_get(f"{WEBMASTER}/user/{user_id}/hosts/{host_id}/diagnostics", token)
        active = {name: info for name, info in diagnostics.get("problems", {}).items()
                  if isinstance(info, dict) and info.get("state") != "ABSENT"}
        lines += [
            f"{host.get('ascii_host_url')}",
            f"  ИКС: {summary.get('sqi')}",
            f"  страниц в поиске: {summary.get('searchable_pages_count')}",
            f"  исключено: {summary.get('excluded_pages_count')}",
            f"  активных проблем: {len(active)}",
        ]
        for name, info in active.items():
            lines.append(f"    {name} — {info.get('severity')} / {info.get('state')}")
    return "\n".join(lines)


def tool_webmaster_queries(arguments):
    token = keychain_token("yandex-webmaster")
    user_id, hosts = _webmaster_host(token)
    limit = min(int(arguments.get("limit", 25)), 100)
    lines = []
    for host in hosts:
        result = http_get(
            f"{WEBMASTER}/user/{user_id}/hosts/{host['host_id']}/search-queries/popular",
            token,
            {"order_by": "TOTAL_SHOWS", "limit": limit,
             "query_indicator": ["TOTAL_SHOWS", "TOTAL_CLICKS", "AVG_SHOW_POSITION"]},
        )
        lines.append(f"{host.get('ascii_host_url')} — запрос: показы / клики / позиция")
        for query in result.get("queries", []):
            indicators = query.get("indicators", {})
            lines.append(
                f"  {query.get('query_text')}: "
                f"{indicators.get('TOTAL_SHOWS') or 0:.0f} / "
                f"{indicators.get('TOTAL_CLICKS') or 0:.0f} / "
                f"{indicators.get('AVG_SHOW_POSITION') or 0:.1f}")
    return "\n".join(lines)


def tool_webmaster_recrawl(arguments):
    urls = arguments.get("urls") or []
    if not urls:
        raise RuntimeError("нужен хотя бы один URL")
    if len(urls) > 20:
        raise RuntimeError("за раз не больше 20 URL — квота Вебмастера 150 в сутки на весь сайт")
    token = keychain_token("yandex-webmaster")
    user_id, hosts = _webmaster_host(token)
    lines = []
    for url in urls:
        host = next((h for h in hosts if _host_matches(url, h)), None)
        if host is None:
            lines.append(f"{url}: нет подтверждённого в Вебмастере хоста для этого URL")
            continue
        post_url = f"{WEBMASTER}/user/{user_id}/hosts/{host['host_id']}/recrawl/queue"
        try:
            result = http_post_json(post_url, token, payload={"url": url}, bearer=False)
            lines.append(f"{url}: поставлен в очередь, task_id {result.get('task_id')}")
        except RuntimeError as error:
            lines.append(f"{url}: {error}")
    return "\n".join(lines)


TOOLS = [
    {
        "name": "webmaster_summary",
        "description": "Состояние сайтов в Яндекс Вебмастере: ИКС, страниц в поиске, "
                       "исключено, список активных проблем диагностики.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_webmaster_summary,
    },
    {
        "name": "webmaster_queries",
        "description": "Поисковые запросы, по которым сайт показывается в Яндексе: "
                       "показы, клики, средняя позиция.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "до 100, по умолчанию 25"}},
        },
        "handler": tool_webmaster_queries,
    },
    {
        "name": "webmaster_recrawl",
        "description": "Ставит URL в очередь на переобход Яндексом (POST, мутирующий вызов — "
                       "единственный в этом сервере). До 20 URL за раз, квота Вебмастера "
                       "150 в сутки на весь сайт.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "urls": {"type": "array", "items": {"type": "string"},
                         "description": "полные адреса, до 20 штук"},
            },
            "required": ["urls"],
        },
        "handler": tool_webmaster_recrawl,
    },
]
