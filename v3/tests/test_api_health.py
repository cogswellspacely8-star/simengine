#!/usr/bin/env python3
"""Tests for GET /api/health and GET /llms.txt — the agent-orientation surface.

Spins the real Handler on an ephemeral port (ThreadingHTTPServer, port 0) so
the routes are exercised exactly as an agent would hit them.
"""

import json
import os
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import server


class TestHealthAndLlmsTxt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path):
        return urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5)

    def test_health_returns_ok(self):
        with self._get("/api/health") as resp:
            self.assertEqual(resp.status, 200)
            payload = json.loads(resp.read())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["engine"], "simengine-v3")
        self.assertIn("/api/simulate", payload["endpoints"])

    def test_llms_txt_served_as_plain_text(self):
        with self._get("/llms.txt") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/plain", resp.headers.get("Content-Type", ""))
            body = resp.read().decode("utf-8")
        self.assertTrue(body.startswith("# SimEngine"))
        self.assertIn("/api/schema", body)


if __name__ == "__main__":
    unittest.main()
