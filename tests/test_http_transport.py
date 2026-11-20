"""Tes transport HTTP ingest.common: header Connection keep-alive.

Server echo lokal (thread, tanpa network eksternal) merekam header
request; HttpClient.get harus mengirim 'Connection: keep-alive' (bukan
'close' paksa urllib) — perbaikan atas pemotongan respons api.jup.ag
oleh egress proxy (diukur worker pasar 2b, 2026-11-20: tanpa header itu
6/6 berhasil, dengan header 1/6).
"""

import http.server
import json
import socketserver
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import common
from ingest.common import HttpClient, RateLimiter, open_url


class _EchoHandler(http.server.BaseHTTPRequestHandler):
    received: dict = {}

    def do_GET(self):
        _EchoHandler.received = dict(self.headers.items())
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TestKeepAliveTransport(unittest.TestCase):
    def _serve_once(self):
        """Jalankan server echo di port bebas; kembalikan (httpd, url)."""
        httpd = socketserver.TCPServer(("127.0.0.1", 0), _EchoHandler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        return httpd, f"http://127.0.0.1:{port}/echo"

    def test_http_client_kirim_keep_alive(self):
        httpd, url = self._serve_once()
        try:
            client = HttpClient(RateLimiter(0))
            result = client.get(url, use_cache=False)
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertEqual(result["status"], 200)
        self.assertEqual(json.loads(result["body"]), {"ok": True})
        self.assertEqual(_EchoHandler.received.get("Connection"), "keep-alive")

    def test_open_url_kirim_keep_alive(self):
        import urllib.request

        httpd, url = self._serve_once()
        try:
            request = urllib.request.Request(url, method="GET")
            with open_url(request, timeout=10) as resp:
                status = resp.status
                resp.read()
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertEqual(status, 200)
        self.assertEqual(_EchoHandler.received.get("Connection"), "keep-alive")


class TestKeepAliveHandlers(unittest.TestCase):
    """Handler memakai kelas koneksi keep-alive (tanpa network).

    Regresi: https_open versi awal membaca self._check_hostname yang
    tidak ada di Python 3.12 (AttributeError saat fetch HTTPS pertama).
    """

    def test_http_handler_memakai_koneksi_keep_alive(self):
        handler = common._KeepAliveHTTPHandler()
        captured: dict = {}

        def fake_do_open(http_class, req, **kwargs):
            captured["http_class"] = http_class
            return "OK"

        with mock.patch.object(handler, "do_open", side_effect=fake_do_open):
            self.assertEqual(handler.http_open(mock.Mock()), "OK")
        self.assertIs(captured["http_class"], common._KeepAliveHTTPConnection)

    def test_https_handler_memakai_koneksi_keep_alive(self):
        handler = common._KeepAliveHTTPSHandler()
        captured: dict = {}

        def fake_do_open(http_class, req, **kwargs):
            captured["http_class"] = http_class
            captured["kwargs"] = kwargs
            return "OK"

        with mock.patch.object(handler, "do_open", side_effect=fake_do_open):
            self.assertEqual(handler.https_open(mock.Mock()), "OK")
        self.assertIs(captured["http_class"], common._KeepAliveHTTPSConnection)
        self.assertIn("context", captured["kwargs"])


if __name__ == "__main__":
    unittest.main()
