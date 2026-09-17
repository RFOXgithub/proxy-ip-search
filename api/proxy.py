"""Thin same-origin proxy from Vercel to the persistent Python backend."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen


class handler(BaseHTTPRequestHandler):
    def _forward(self) -> None:
        backend = os.environ.get("BACKEND_URL", "").strip().rstrip("/")
        if not backend.startswith("https://"):
            self._json(503, {"error": "BACKEND_URL belum dikonfigurasi dengan URL HTTPS."})
            return

        request_url = urlsplit(self.path)
        query = parse_qs(request_url.query, keep_blank_values=True)
        upstream_path = query.pop("path", [""])[0].lstrip("/")
        upstream = f"{backend}/api/{upstream_path}"
        if query:
            upstream += "?" + urlencode(query, doseq=True)

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        headers = {"Accept": "application/json"}
        if self.headers.get("Content-Type"):
            headers["Content-Type"] = self.headers["Content-Type"]
        request = Request(upstream, data=body, headers=headers, method=self.command)
        try:
            with urlopen(request, timeout=15) as response:
                payload, status = response.read(), response.status
                content_type = response.headers.get("Content-Type", "application/json")
        except HTTPError as exc:
            payload, status = exc.read(), exc.code
            content_type = exc.headers.get("Content-Type", "application/json")
        except (URLError, TimeoutError):
            self._json(502, {"error": "Backend tidak dapat dijangkau."})
            return

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, data: dict[str, str]) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _forward
    do_POST = _forward
