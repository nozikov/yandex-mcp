"""Всё про доступ: где лежат секреты, какой токен брать и как войти.

  store.py     — выбор хранилища: Keychain / secret-tool / файл 0600
  tokens.py    — токен сервиса, с фолбэком на общий токен единого входа
  flow.py      — PKCE-вход в Яндекс
  callback.py  — приём redirect на localhost

Команды пользователя живут в `yandex_mcp.cli` (`yandex-mcp login|setup`).

Инвариант: значение секрета никогда не печатается в stdout/stderr — только
отпечаток sha256:xxxxxxxx.
"""
