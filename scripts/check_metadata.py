#!/usr/bin/env python3
"""Проверка согласованности метаданных перед публикацией.

Три файла описывают один и тот же пакет, и разъехаться они умеют молча:
реестр MCP проверяет владение по строке `mcp-name` в README, а версию берёт
из server.json — если она отстанет от pyproject.toml, публикация уедет
не туда. Раньше похожая рассинхронизация уже случилась с версией сервера.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))

    name, version = server["name"], server["version"]
    problems = []

    if f"mcp-name: {name}" not in readme:
        problems.append(f"в README нет строки `mcp-name: {name}` — по ней реестр MCP "
                        "проверяет владение PyPI-пакетом")

    if f'version = "{version}"' not in pyproject:
        problems.append(f"версия в server.json ({version}) разошлась с pyproject.toml")

    if plugin["version"] != version:
        problems.append(f"версия в .claude-plugin/plugin.json ({plugin['version']}) "
                        f"разошлась с server.json ({version})")

    # реестр MCP режет описание на 100 символах и отдаёт 422 уже при публикации
    if len(server["description"]) > 100:
        problems.append(f"описание в server.json длиннее 100 символов "
                        f"({len(server['description'])}) — реестр MCP такое не примет")

    for package in server.get("packages", []):
        if package.get("version") != version:
            problems.append(f"версия пакета {package.get('identifier')} в server.json "
                            "разошлась с версией сервера")

    sys.path.insert(0, str(ROOT / "src"))
    from yandex_mcp.registry import TOOL_SCHEMAS          # noqa: E402
    from yandex_mcp.server import SERVER_INFO             # noqa: E402

    if SERVER_INFO["version"] != version:
        problems.append(f"SERVER_INFO отдаёт {SERVER_INFO['version']}, "
                        f"а пакет собирается как {version}")

    count = len(TOOL_SCHEMAS)
    if not re.search(rf"\b{count} инструмент", readme):
        problems.append(f"инструментов сейчас {count}, а README называет другое число")

    # README — это документация к коду, и расходиться они умеют молча
    for tool in TOOL_SCHEMAS:
        if f"`{tool['name']}`" not in readme:
            problems.append(f"инструмент {tool['name']} есть в коде, но не описан в README")

    documented = set(re.findall(r"YANDEX_MCP_[A-Z_]+", readme))
    used = set(re.findall(r"YANDEX_MCP_[A-Z_]+", "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "src").rglob("*.py"))))
    # SECRET_* — это префикс, конкретные имена собираются на лету
    used = {name for name in used if not name.startswith("YANDEX_MCP_SECRET_")}
    documented = {name for name in documented if not name.startswith("YANDEX_MCP_SECRET_")}
    for name in sorted(used - documented):
        problems.append(f"код читает {name}, но README о ней молчит")
    for name in sorted(documented - used):
        problems.append(f"README обещает {name}, но код её не читает")

    # картинки в README ломаются молча: файла нет — GitHub рисует пустую рамку
    for path in re.findall(r'(?:src|srcset)="(docs/[^"]+)"', readme):
        if not (ROOT / path).exists():
            problems.append(f"README ссылается на {path}, а файла нет — "
                            "пересобери диаграммы: python3 scripts/make_diagrams.py")

    if problems:
        for problem in problems:
            print("✗", problem, file=sys.stderr)
        return 1
    print(f"ok: {name} {version}, инструментов {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
