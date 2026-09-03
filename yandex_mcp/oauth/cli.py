"""Обратная совместимость: команда `yandex-oauth` из ранних версий.

Вся функциональность переехала в `yandex-mcp login|setup|status|logout`.
Этот шим переводит старые вызовы на новый CLI, чтобы у тех, кто уже прописал
`yandex-oauth` в своих скриптах, ничего не сломалось.
"""

import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print("yandex-oauth устарел, используй `yandex-mcp login` "
          "(setup/status/logout — там же)", file=sys.stderr)

    from ..cli import main as cli_main

    if not argv:
        return cli_main(["login"])

    command, rest = argv[0], argv[1:]
    if command == "login":
        # старый --name задавал имя записи в Keychain, старый --scope — права;
        # теперь и то и другое выводится из выбранных сервисов, так что отбрасываем
        forwarded = []
        skip_next = False
        for item in rest:
            if skip_next:
                skip_next = False
                continue
            if item in ("--name", "--scope"):
                skip_next = True
                continue
            forwarded.append(item)
        return cli_main(["login"] + forwarded)
    if command == "exchange":
        code = rest[rest.index("--code") + 1] if "--code" in rest else None
        return cli_main(["login", "--exchange", code] if code else ["login"])
    if command == "status":
        return cli_main(["status"])
    if command == "refresh":
        print("refresh больше не нужен: токен PKCE живёт около года — "
              "когда истечёт, выполни `yandex-mcp login`", file=sys.stderr)
        return cli_main(["status"])
    return cli_main(argv)


if __name__ == "__main__":
    main()
