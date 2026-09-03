"""Локальный HTTP-приёмник redirect от oauth.yandex.ru (режим без --manual).

Яндекс возвращает сюда либо код подтверждения, либо ошибку — например
`invalid_scope`, если приложению не выдано запрошенное право (частый случай:
`direct:api` без одобренной заявки в Директе).
"""

import http.server
import urllib.parse


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    code = None
    state = None
    error = None
    error_description = None

    @classmethod
    def reset(cls):
        cls.code = cls.state = cls.error = cls.error_description = None

    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        CallbackHandler.code = params.get("code", [None])[0]
        CallbackHandler.state = params.get("state", [None])[0]
        CallbackHandler.error = params.get("error", [None])[0]
        CallbackHandler.error_description = params.get("error_description", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if CallbackHandler.code:
            message = "Готово, вернись в терминал."
        elif CallbackHandler.error:
            message = "Яндекс отказал — подробности в терминале."
        else:
            message = "Код не получен."
        self.wfile.write(f"<html><body><h3>{message}</h3></body></html>".encode())

    def log_message(self, *args):
        pass  # URL с кодом не должен попасть в вывод
