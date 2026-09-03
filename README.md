# yandex-mcp

MCP-сервер для read-only доступа к Яндекс Метрике, Вебмастеру и Директу (включая Wordstat) —
чтобы LLM-агент мог сам посмотреть аналитику сайта, вместо того чтобы вы копировали цифры
из кабинетов вручную.

Написан на чистом Python **без рантайм-зависимостей**: JSON-RPC поверх stdio реализован
здесь же, чтобы OAuth-токен не проходил через сторонние пакеты.

## Почему так, а не через готовый SDK

- **Токен нигде не хардкожен и не пишется на диск в открытом виде.** Он лежит в macOS
  Keychain и достаётся в момент вызова через `security find-generic-password`. Ни в одном
  ответе инструмента, ни в тексте ошибки значение токена не появляется — есть отдельный
  `scrub()`, который вычищает Bearer/OAuth-заголовки и Яндекс-токены (`y0_...`, `y1_...`)
  из любого текста перед тем, как он уйдёт наружу.
- **Почти всё — чтение.** Единственный мутирующий вызов — `webmaster_recrawl` (постановка
  URL в очередь на переобход), и он ограничен 20 URL за раз: у Вебмастера квота 150 в сутки
  на весь сайт, тратить её молча нельзя.
- **Данные из API считаются недоверенными.** Поисковые фразы, UTM-метки, названия кампаний
  и заголовки страниц пишут посторонние люди. Каждый ответ инструмента снабжается пометкой:
  если внутри данных встретится текст, похожий на инструкцию агенту, — это нужно процитировать
  пользователю, а не выполнять.
- **Официальный MCP SDK не используется намеренно** — он тянет `httpx`, `pydantic`, `anyio`
  и их транзитивные зависимости, а через этот процесс проходит OAuth-токен к вашей аналитике
  и рекламному кабинету. Меньше чужого кода в рантайме — меньше supply-chain поверхность.

## Инструменты

| Инструмент | Что делает |
|---|---|
| `metrika_summary` | Сводка за период: визиты, посетители, отказы, длительность визита, глубина, достижения всех целей счётчика |
| `metrika_report` | Произвольный отчёт Reporting API Метрики — любые метрики/измерения/фильтры |
| `metrika_compare` | Сравнение метрик между двумя периодами (по умолчанию — с предыдущим таким же по длине), опционально построчно по измерению |
| `metrika_counters` | Список доступных счётчиков с сайтами и статусом |
| `webmaster_summary` | ИКС, страниц в поиске, исключено, активные проблемы диагностики по всем подтверждённым сайтам |
| `webmaster_queries` | Поисковые запросы: показы, клики, средняя позиция |
| `webmaster_indexing` | Динамика количества страниц в поиске по датам |
| `webmaster_sitemaps` | Sitemap-файлы, которые видит Яндекс: URL, число адресов, ошибки, дата обращения робота |
| `webmaster_recrawl` | Постановка URL в очередь на переобход (единственный мутирующий вызов, до 20 URL) |
| `direct_campaigns` | Список кампаний Директа (только чтение) и остаток баллов API |
| `direct_report` | Отчёт Reports API v5 — расход, показы, клики, CTR по кампаниям/объявлениям/группам/поисковым запросам |
| `wordstat_phrases` | Частотности Вордстата через Live v4 API Директа (новый Wordstat API требует сервисного аккаунта Cloud, поэтому через Live v4) |

## Структура проекта

```
yandex-mcp/
  yandex_mcp/            # MCP-сервер
    scrub.py             # вычищение секретов из ответов/ошибок
    keychain.py          # чтение OAuth-токена из macOS Keychain
    httpclient.py         # urllib-обёртка: заголовки, единая обработка ошибок
    server.py             # JSON-RPC/stdio диспетчер, точка входа main()
    tools/
      metrika.py
      webmaster.py
      direct.py
      wordstat.py
  yandex_oauth/            # CLI получения/обновления OAuth-токенов
    keychain.py
    callback.py            # локальный HTTP-приёмник redirect (режим без --manual)
    oauth.py                # PKCE-флоу, обмен кода на токены
    cli.py                   # argparse, точка входа main()
  tests/
  pyproject.toml
```

Ни `yandex_mcp`, ни `yandex_oauth` не тянут внешних библиотек в рантайме — `pytest` в
`[project.optional-dependencies].dev` нужен только для тестов.

## Требования

- macOS (используется `security` из Keychain Services — на Linux/Windows работать не будет
  без замены `keychain.py` на другой бэкенд, например `secret-tool`/libsecret или
  Windows Credential Manager)
- Python 3.8+
- OAuth-приложение на [oauth.yandex.ru](https://oauth.yandex.ru/) с нужными правами
  (Метрика, Вебмастер, Директ — под то, что собираетесь использовать)

## Установка

```bash
git clone <this-repo>
cd yandex-mcp
pip install -e .
```

Это регистрирует команды `yandex-mcp` и `yandex-oauth` в текущем окружении (`PATH`).
Без установки сервер тоже запускается — из корня репозитория:

```bash
python3 -m yandex_mcp
```

### 1. Завести OAuth-приложение

На [oauth.yandex.ru](https://oauth.yandex.ru/client/new) создайте приложение с нужными
правами (`metrika:read`, `webmaster:hosts:read-write`, `direct:api` и т.д.). Redirect URI
можно оставить дефолтным (`https://oauth.yandex.ru/verification_code`) — тогда авторизация
идёт в режиме `--manual`.

Сохраните client_id/client_secret в Keychain:

```bash
security add-generic-password -s yandex-oauth-client-id     -a "$USER" -w
security add-generic-password -s yandex-oauth-client-secret -a "$USER" -w
```

### 2. Получить токены

Под каждый сервис — свой именованный токен (имя нужно и в `login`, и в конфиге MCP-клиента,
см. ниже):

```bash
yandex-oauth login --name yandex-metrika   --scope "metrika:read" --manual
yandex-oauth login --name yandex-webmaster --scope "webmaster:hosts:read-write" --manual
yandex-oauth login --name yandex-direct    --scope "direct:api" --manual
```

Токен и refresh-токен уйдут в Keychain как `<name>-token` / `<name>-refresh` / `<name>-expires`.
В stdout попадает только sha256-отпечаток — сам токен не печатается никогда.

Продлить, когда истечёт:

```bash
yandex-oauth refresh --name yandex-metrika
yandex-oauth status  --name yandex-metrika
```

### 3. Подключить к MCP-клиенту

Пример для Claude Code (`.mcp.json` или `claude mcp add`) — см. [`.mcp.json.example`](./.mcp.json.example):

```json
{
  "mcpServers": {
    "yandex": {
      "command": "yandex-mcp",
      "env": {
        "YANDEX_MCP_DEFAULT_COUNTER": "12345678"
      }
    }
  }
}
```

Команда `yandex-mcp` должна быть на `PATH` (см. установку выше); если ставили в venv —
укажите полный путь до него, например `/path/to/yandex-mcp/.venv/bin/yandex-mcp`.

`YANDEX_MCP_DEFAULT_COUNTER` — опционален: если не задать, `counter_id` придётся передавать
в каждом вызове `metrika_summary`/`metrika_report` явно.

## Тесты

```bash
pip install -e ".[dev]"
pytest
```

Тесты мокают Keychain и сеть (`keychain_token`/`http_get`/`http_post_json`/`perform`
подменяются через `monkeypatch`) — реальных вызовов к API и Keychain не делают.

## Ограничения

- Хранилище токенов — только macOS Keychain. Порт под Linux (`secret-tool`/libsecret) или
  Windows (Credential Manager) — вопрос замены `keychain_token`/`keychain_get`/`keychain_set`
  на соответствующий бэкенд.
- `direct_campaigns`, `direct_report` и `wordstat_phrases` требуют доступа к API Директа —
  пока заявка на доступ не одобрена, Директ отвечает кодом ошибки 58.
- `direct_report` при офлайн-обработке (Reports API решает сам, online или offline) может
  готовиться минуты — тул сам поллит и ждёт, но упирается в квоту Директа: не больше 5
  офлайн-отчётов в очереди на аккаунт одновременно.
- `webmaster_sitemaps` отдаёт первые 100 sitemap хоста (без пагинации) — для сайтов с
  большим индекс-sitemap-деревом видна только верхняя часть.
- Ответ каждого инструмента обрезается до 20000 символов — для больших выгрузок сужайте
  период или `limit`.
- `yandex-oauth` пишет токен в Keychain через `security add-generic-password -w <value>` —
  значение передаётся аргументом командной строки, поэтому на время работы этого подпроцесса
  токен виден в списке процессов (`ps -ww`) любому, у кого есть доступ к той же машине.
  Это ограничение самого `security` CLI (он не читает секрет из stdin), а не то, что можно
  обойти в коде сервера — учитывайте на многопользовательских машинах.

## Лицензия

MIT
