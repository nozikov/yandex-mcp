"""HTTP-обёртка над urllib: OAuth/Bearer-заголовки и единая обработка ошибок."""

import json
import urllib.error
import urllib.parse
import urllib.request

from .scrub import scrub


def http_get(url, token, params=None, bearer=False):
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    scheme = "Bearer" if bearer else "OAuth"
    request = urllib.request.Request(url, headers={"Authorization": f"{scheme} {token}"})
    return perform(request)


def http_post_json(url, token, payload, bearer=True, headers_out=None):
    headers = {
        "Authorization": f"{'Bearer' if bearer else 'OAuth'} {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept-Language": "ru",
    }
    body = json.dumps(payload, ensure_ascii=False).encode()
    return perform(urllib.request.Request(url, data=body, headers=headers, method="POST"),
                   headers_out=headers_out)


def perform(request, headers_out=None):
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if headers_out is not None:
                headers_out.update(dict(response.headers))
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = scrub(error.read().decode(errors="replace")[:600])
        raise RuntimeError(f"API вернул HTTP {error.code}: {detail}")
    except urllib.error.URLError as error:
        raise RuntimeError(f"сеть недоступна: {error.reason}")
