"""Сборка реестра тулов из отдельных модулей по сервисам."""

from . import direct, metrika, webmaster, wordstat

TOOLS = metrika.TOOLS + webmaster.TOOLS + direct.TOOLS + wordstat.TOOLS

HANDLERS = {tool["name"]: tool["handler"] for tool in TOOLS}
TOOL_SCHEMAS = [{key: tool[key] for key in ("name", "description", "inputSchema")} for tool in TOOLS]
