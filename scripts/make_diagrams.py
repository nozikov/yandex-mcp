#!/usr/bin/env python3
"""Генератор SVG-диаграмм для README.

Пара файлов на диаграмму — светлая и тёмная: GitHub подставляет нужную через
<picture> и prefers-color-scheme. Палитра взята из тем самого GitHub, чтобы
картинки не выбивались из страницы.
"""

import pathlib

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"

THEMES = {
    "light": dict(ink="#1f2328", muted="#59636e", rule="#d1d9e0", surface="#f6f8fa",
                  client="#0969da", client_bg="#ddf4ff",
                  serv="#9a6700", serv_bg="#fff8c5",
                  yx="#cf222e", yx_bg="#ffebe9",
                  ok="#1a7f37", ok_bg="#dafbe1"),
    "dark": dict(ink="#e6edf3", muted="#9198a1", rule="#3d444d", surface="#151b23",
                 client="#4493f8", client_bg="#121d2f",
                 serv="#d29922", serv_bg="#282215",
                 yx="#f85149", yx_bg="#25171c",
                 ok="#3fb950", ok_bg="#12261e"),
}

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace"


def head(width, height, c):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img">
<style>
  .t {{ font-family: {FONT}; }}
  .m {{ font-family: {MONO}; }}
  .title {{ font-size: 15px; font-weight: 600; }}
  .sub {{ font-size: 12px; fill: {c["muted"]}; }}
  .lbl {{ font-size: 12px; fill: {c["muted"]}; }}
  .step {{ font-size: 13px; fill: {c["ink"]}; }}
  .cap {{ font-size: 11px; letter-spacing: .1em; fill: {c["muted"]}; }}
  .box {{ stroke-width: 1.5; }}
  .arrow {{ stroke: {c["muted"]}; stroke-width: 1.5; fill: none; }}
</style>
<defs>
  <marker id="a" markerWidth="8" markerHeight="6" refX="7.5" refY="3" orient="auto">
    <path d="M0 0 L8 3 L0 6 z" fill="{c["muted"]}"/>
  </marker>
</defs>
'''


def box(x, y, w, h, c, kind, title, lines):
    fill, stroke = c[f"{kind}_bg"], c[kind]
    cx = x + w / 2
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" class="box" fill="{fill}" stroke="{stroke}"/>',
           f'<text class="t title" x="{cx}" y="{y + 26}" text-anchor="middle" fill="{stroke}">{title}</text>']
    for i, line in enumerate(lines):
        out.append(f'<text class="t sub" x="{cx}" y="{y + 48 + i * 17}" text-anchor="middle">{line}</text>')
    return "\n".join(out)


def how_it_works(c):
    s = [head(860, 250, c)]
    # рамка «твой компьютер» охватывает клиент и сервер, но не Яндекс
    s.append(f'<rect x="8" y="34" width="548" height="172" rx="8" fill="none" '
             f'stroke="{c["rule"]}" stroke-width="1.5" stroke-dasharray="5 5"/>')
    s.append('<text class="t cap" x="24" y="24">ТВОЙ КОМПЬЮТЕР</text>')
    s.append(box(20, 62, 228, 130, c, "client", "MCP-клиент",
                 ["Claude Code, Cursor,", "VS Code", "", "спрашивает словами"]))
    s.append(box(304, 62, 236, 130, c, "serv", "yandex-mcp",
                 ["Python без зависимостей", "", "токен в хранилище ОС,", "наружу не отдаётся"]))
    s.append(box(604, 62, 240, 130, c, "yx", "API Яндекса",
                 ["Метрика, Вебмастер,", "Директ, Вордстат", "", "только чтение"]))
    # зазоры между блоками намеренно шире подписей, иначе текст ложится на рамку
    s.append('<path class="arrow" d="M252 112 L300 112" marker-end="url(#a)"/>')
    s.append('<path class="arrow" d="M300 142 L252 142" marker-end="url(#a)" stroke-dasharray="4 3"/>')
    s.append('<text class="m lbl" x="276" y="100" text-anchor="middle" font-size="11">stdio</text>')
    s.append('<path class="arrow" d="M544 112 L600 112" marker-end="url(#a)"/>')
    s.append('<path class="arrow" d="M600 142 L544 142" marker-end="url(#a)" stroke-dasharray="4 3"/>')
    s.append('<text class="m lbl" x="572" y="100" text-anchor="middle" font-size="11">https</text>')
    s.append('<text class="t sub" x="430" y="232" text-anchor="middle">'
             'Данные идут напрямую от Яндекса к тебе. Посредников нет.</text>')
    s.append("</svg>")
    return "\n".join(s)


def login(c):
    s = [head(860, 200, c)]
    steps = [
        ("1", "Скажи агенту", ["«Подключи Яндекс»"]),
        ("2", "Открой ссылку", ["и подтверди доступ", "в браузере Яндекса"]),
        ("3", "Верни код в чат", ["Яндекс покажет его", "на странице"]),
    ]
    for i, (num, title, lines) in enumerate(steps):
        x = 20 + i * 270
        s.append(f'<circle cx="{x + 22}" cy="46" r="15" fill="{c["client_bg"]}" stroke="{c["client"]}" stroke-width="1.5"/>')
        s.append(f'<text class="m" x="{x + 22}" y="51" text-anchor="middle" font-size="14" font-weight="600" fill="{c["client"]}">{num}</text>')
        s.append(f'<text class="t" x="{x + 50}" y="44" font-size="14" font-weight="600" fill="{c["ink"]}">{title}</text>')
        for j, line in enumerate(lines):
            s.append(f'<text class="t sub" x="{x + 50}" y="{64 + j * 16}">{line}</text>')
        if i < 2:
            s.append(f'<path class="arrow" d="M{x + 232} 46 L{x + 262} 46" marker-end="url(#a)"/>')
    s.append(f'<rect x="20" y="118" width="820" height="58" rx="6" fill="{c["ok_bg"]}" stroke="{c["ok"]}" stroke-width="1.5"/>')
    s.append(f'<text class="t" x="430" y="143" text-anchor="middle" font-size="14" font-weight="600" fill="{c["ok"]}">Токен лёг в хранилище операционной системы</text>')
    s.append(f'<text class="t sub" x="430" y="163" text-anchor="middle">Терминал не нужен. Перезапускать сервер не нужно. Действует около года.</text>')
    s.append("</svg>")
    return "\n".join(s)


def storage(c):
    s = [head(860, 250, c)]
    s.append(f'<text class="t cap" x="20" y="22">ХРАНИЛИЩЕ ВЫБИРАЕТСЯ САМО — СВЕРХУ ВНИЗ, ДО ПЕРВОГО ПОДХОДЯЩЕГО</text>')
    rows = [
        ("Переменная окружения", "если задана — Docker и CI", "serv"),
        ("Keychain", "macOS", "ok"),
        ("secret-tool", "Linux: GNOME Keyring, KWallet", "ok"),
        ("файл с правами 0600", "Windows, сервер без графики, контейнер", "serv"),
    ]
    for i, (name, note, kind) in enumerate(rows):
        y = 42 + i * 46
        s.append(f'<rect x="20" y="{y}" width="820" height="36" rx="6" fill="{c[kind + "_bg"]}" stroke="{c[kind]}" stroke-width="1.5"/>')
        s.append(f'<text class="m" x="40" y="{y + 23}" font-size="13" font-weight="600" fill="{c[kind]}">{name}</text>')
        s.append(f'<text class="t sub" x="820" y="{y + 23}" text-anchor="end">{note}</text>')
        if i < 3:
            s.append(f'<path class="arrow" d="M40 {y + 36} L40 {y + 46}" marker-end="url(#a)"/>')
    s.append(f'<text class="t sub" x="20" y="240">'
             f'Токен не появляется ни в ответе инструмента, ни в тексте ошибки — есть отдельный фильтр.</text>')
    s.append("</svg>")
    return "\n".join(s)


def main():
    DOCS.mkdir(exist_ok=True)
    for name, draw in (("how-it-works", how_it_works), ("login", login), ("token-storage", storage)):
        for theme, colors in THEMES.items():
            path = DOCS / f"{name}-{theme}.svg"
            path.write_text(draw(colors), encoding="utf-8")
            print("написано", path.name, path.stat().st_size, "байт")


if __name__ == "__main__":
    main()
