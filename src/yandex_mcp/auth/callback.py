"""Локальный HTTP-приёмник redirect от oauth.yandex.ru (режим без --manual)."""

import http.server
import urllib.parse


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    code = None
    state = None

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        CallbackHandler.code = params.get("code", [None])[0]
        CallbackHandler.state = params.get("state", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        message = "Готово, вернись в терминал." if CallbackHandler.code else "Код не получен."
        self.wfile.write(f"<html><body><h3>{message}</h3></body></html>".encode())

    def log_message(self, *args):
        pass  # URL с кодом не должен попасть в вывод
