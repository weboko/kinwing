"""The reader's HTTP API: views, writes, and its private-by-default protections."""

import json
import os
import threading
import unittest
import urllib.error
import urllib.request

from tests.util import DOC, KwTestCase
from kinwing import reader


class ReaderTest(KwTestCase):
    def setUp(self):
        super().setUp()
        os.environ["KW_READER_QUIET"] = "1"
        self.topic()
        self.sid = self.source_from_text(DOC)["id"]
        e = self.kb.add_evidence(self.sid, "FSRS models memory with three components", "t1")
        self.kb.add_concept("t1", "Stability", cid="stability", summary="How long a memory lasts.",
                            explanation="Stability is **measured** in days. <script>alert(1)</script> [x](javascript:alert(1))",
                            prompts=["explain:What is it?"])
        self.kb.add_claim("t1", "FSRS has three variables", support=[e["id"]], concepts="stability")
        self.start()

    def start(self, token=""):
        if token:
            os.environ["KW_READER_TOKEN"] = token
        else:
            os.environ.pop("KW_READER_TOKEN", None)
        self.srv = reader.make_server(self.kb, "127.0.0.1", 0)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        os.environ.pop("KW_READER_TOKEN", None)
        super().tearDown()

    def req(self, method, path, body=None, headers=None):
        h = {"Content-Type": "application/json"}
        if method != "GET":
            h["X-KW"] = "1"
        h.update(headers or {})
        data = json.dumps(body).encode() if body is not None else (b"{}" if method != "GET" else None)
        r = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(r) as resp:
                raw = resp.read()
                body = json.loads(raw or b"{}") if "json" in resp.headers.get("Content-Type", "") else raw
                return resp.status, body, resp.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), e.headers

    def test_views(self):
        code, home, headers = self.req("GET", "/api/home")
        self.assertEqual(code, 200)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(home["topics"][0]["id"], "t1")
        code, t, _ = self.req("GET", "/api/topic/t1")
        self.assertEqual(t["concepts"][0]["id"], "stability")
        self.assertEqual(t["claims"][0]["support"][0]["source"], self.sid)  # navigable to the source
        code, c, _ = self.req("GET", "/api/concept/stability")
        self.assertIn("<strong>measured</strong>", c["explanation_html"])
        self.assertNotIn("<script>", c["explanation_html"])             # agent text is escaped
        self.assertNotIn("javascript:", c["explanation_html"])
        code, s, _ = self.req("GET", f"/api/source/{self.sid}")
        self.assertEqual(s["total_paragraphs"], 4)
        self.assertEqual(s["evidence"][0]["para"], 2)
        code, page, _ = self.req("GET", "/")
        self.assertEqual(code, 200)

    def test_writes_persist(self):
        self.assertEqual(self.req("POST", "/api/progress", {"kind": "source", "id": self.sid, "fraction": 0.5, "para": 3})[0], 200)
        code, s, _ = self.req("GET", f"/api/source/{self.sid}")
        self.assertEqual(s["state"]["observed"]["para"], 3)                 # resume position
        code, h, _ = self.req("POST", "/api/highlights", {"kind": "source", "id": self.sid,
                              "quote": "three components", "note": "nice"})
        self.assertEqual(h["quote_origin"], "source text (exact)")
        code, r, _ = self.req("POST", "/api/ask", {"kind": "deeper", "text": "how is D estimated?", "concept": "stability"})
        q = self.kb.load("question", r["question"]["id"])[0]
        self.assertEqual((q["origin"], q["asked_by"]), ("learning", "user"))
        code, _, _ = self.req("POST", "/api/mark", {"concept": "stability", "value": "known"})
        self.assertEqual(self.req("GET", "/api/next")[1]["next"], [])
        code, ex, _ = self.req("POST", "/api/export", {"highlights": [h["id"]], "concepts": []})
        self.assertEqual(code, 200)
        self.assertTrue(any(f["path"].endswith(".md") for f in ex["files"]))
        self.assertEqual(self.req("PATCH", f"/api/highlights/{h['id']}", {"note": "edited"})[1]["note"], "edited")
        self.assertEqual(self.req("DELETE", f"/api/highlights/{h['id']}")[0], 200)

    def test_write_requires_custom_header(self):
        code, body, _ = self.req("POST", "/api/mark", {"concept": "stability", "value": "known"}, headers={"X-KW": "0"})
        self.assertEqual(code, 403)

    def test_cross_origin_write_refused(self):
        code, _, _ = self.req("POST", "/api/mark", {"concept": "stability", "value": "known"},
                              headers={"Origin": "http://evil.example"})
        self.assertEqual(code, 403)

    def test_dns_rebinding_host_refused(self):
        code, _, _ = self.req("GET", "/api/home", headers={"Host": "attacker.example:8765"})
        self.assertEqual(code, 403)

    def test_token(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.start(token="s3cret")
        self.assertEqual(self.req("GET", "/api/home")[0], 401)
        self.assertEqual(self.req("GET", "/api/home", headers={"Cookie": "kw_token=wrong"})[0], 401)
        self.assertEqual(self.req("GET", "/api/home", headers={"Cookie": "kw_token=s3cret"})[0], 200)

    def test_static_path_traversal(self):
        code, _, _ = self.req("GET", "/static/../reader.py")
        self.assertEqual(code, 404)


if __name__ == "__main__":
    unittest.main()
