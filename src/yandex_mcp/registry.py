"""Реестр инструментов: сборка TOOLS/HANDLERS из модулей по сервисам."""

from .tools import auth, direct, metrika, webmaster, wordstat

TOOLS = (metrika.TOOLS + webmaster.TOOLS + direct.TOOLS + wordstat.TOOLS
         + auth.TOOLS)

HANDLERS = {tool["name"]: tool["handler"] for tool in TOOLS}
TOOL_SCHEMAS = [{key: tool[key] for key in ("name", "description", "inputSchema")} for tool in TOOLS]
