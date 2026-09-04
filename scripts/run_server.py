#!/usr/bin/env python3
"""Запуск MCP-сервера прямо из клона репозитория, без установки пакета.

Нужен плагину Claude Code: он получает каталог репозитория в
${CLAUDE_PLUGIN_ROOT} и запускает этот файл. Зависимостей у сервера нет,
поэтому достаточно добавить src/ в путь импорта.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "src"))

from yandex_mcp.cli import main  # noqa: E402  — только после правки sys.path

if __name__ == "__main__":
    main()
