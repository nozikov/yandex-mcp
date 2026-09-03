# yandex-mcp

MCP-сервер для read-only доступа к Яндекс Метрике, Вебмастеру и Директу (включая Wordstat) —
чтобы LLM-агент мог сам посмотреть аналитику сайта, вместо того чтобы вы копировали цифры
из кабинетов вручную.

Написан на чистом Python без зависимостей: JSON-RPC поверх stdio реализован в одном файле,
чтобы OAuth-токен не проходил через сторонние пакеты.

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

## Инструменты

| Инструмент | Что делает |
|---|---|
| `metrika_summary` | Сводка за период: визиты, посетители, отказы, длительность визита, глубина, достижения всех целей счётчика |
| `metrika_report` | Произвольный отчёт Reporting API Метрики — любые метрики/измерения/фильтры |
| `metrika_counters` | Список доступных счётчиков с сайтами и статусом |
| `webmaster_summary` | ИКС, страниц в поиске, исключено, активные проблемы диагностики по всем подтверждённым сайтам |
| `webmaster_queries` | Поисковые запросы: показы, клики, средняя позиция |
| `webmaster_recrawl` | Постановка URL в очередь на переобход (единственный мутирующий вызов, до 20 URL) |
| `direct_campaigns` | Список кампаний Директа (только чтение) и остаток баллов API |
| `wordstat_phrases` | Частотности Вордстата через Live v4 API Директа (новый Wordstat API требует сервисного аккаунта Cloud, поэтому через Live v4) |

## Требования

- macOS (используется `security` из Keychain Services — на Linux/Windows работать не будет
  без замены хранилища токенов)
- Python 3.8+, без внешних зависимостей
- OAuth-приложение на [oauth.yandex.ru](https://oauth.yandex.ru/) с нужными правами
  (Метрика, Вебмастер, Директ — под то, что собираетесь использовать)

## Установка

```bash
git clone <this-repo>
cd yandex-mcp
chmod +x yandex-mcp yandex-oauth
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
./yandex-oauth login --name yandex-metrika  --scope "metrika:read" --manual
./yandex-oauth login --name yandex-webmaster --scope "webmaster:hosts:read-write" --manual
./yandex-oauth login --name yandex-direct   --scope "direct:api" --manual
```

Токен и refresh-токен уйдут в Keychain как `<name>-token` / `<name>-refresh` / `<name>-expires`.
В stdout попадает только sha256-отпечаток — сам токен не печатается никогда.

Продлить, когда истечёт:

```bash
./yandex-oauth refresh --name yandex-metrika
./yandex-oauth status  --name yandex-metrika
```

### 3. Подключить к MCP-клиенту

Пример для Claude Code (`.mcp.json` или `claude mcp add`) — см. [`.mcp.json.example`](./.mcp.json.example):

```json
{
  "mcpServers": {
    "yandex": {
      "command": "/absolute/path/to/yandex-mcp/yandex-mcp",
      "env": {
        "YANDEX_MCP_DEFAULT_COUNTER": "12345678"
      }
    }
  }
}
```

`YANDEX_MCP_DEFAULT_COUNTER` — опционален: если не задать, `counter_id` придётся передавать
в каждом вызове `metrika_summary`/`metrika_report` явно.

## Ограничения

- Хранилище токенов — только macOS Keychain. Порт под Linux (`secret-tool`/libsecret) или
  Windows (Credential Manager) — вопрос замены `keychain_token`/`keychain_get`/`keychain_set`
  на соответствующий бэкенд.
- `direct_campaigns` и `wordstat_phrases` требуют доступа к API Директа — пока заявка на
  доступ не одобрена, Директ отвечает кодом ошибки 58.
- Ответ каждого инструмента обрезается до 20000 символов — для больших выгрузок сужайте
  период или `limit`.

## Лицензия

MIT
