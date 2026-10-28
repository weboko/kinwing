"""create-report integration and the public/private boundary."""

import os
import unittest

from tests.util import DOC, KwTestCase, StaticServer
from kinwing import export, ingest, report
from kinwing.learning import Learning
from kinwing.store import KwError, Paths


class ReportTest(KwTestCase):
    def setUp(self):
        super().setUp()
        self.topic(objective="I want to finally understand why my Anki reviews pile up",
                   familiarity="I have used Anki daily for six years")
        site = self.tmp / "site"
        site.mkdir()
        (site / "doc.md").write_text(DOC)
        self.srv = StaticServer(site)
        self.pub = ingest.add_source(self.kb, "t1", url=self.srv.url + "/doc.md", rights="open")["id"]
        self.priv = self.source_from_text("# My private notes\n\nPersonal diary about my study habits.\n",
                                          name="diary.md", title="My private study diary")["id"]
        e1 = self.kb.add_evidence(self.pub, "FSRS models memory with three components", "t1")
        e2 = self.kb.add_evidence(self.priv, "Personal diary about my study habits.", "t1")
        self.kb.add_claim("t1", "FSRS has three memory variables", support=[e1["id"]], strength="strong")
        self.kb.add_claim("t1", "The user studies irregularly", support=[e2["id"]], strength="strong")
        (self.p.topic_dir("t1") / "overview.md").write_text("# T\n\nFSRS is a three-variable memory model. It schedules reviews.\n")
        self.L = Learning(self.kb)
        self.kb.add_concept("t1", "Stability", cid="stability", summary="How long a memory lasts.")
        self.L.add_highlight("concept", "stability", "How long", note="This reminds me of my own forgetting at work.")
        self.L.add_answer("stability", "What is it?", "My personal explanation of stability in my words.")
        self.L.ask("question", "Does this apply to how I learn Japanese kanji?", concept="stability")

    def tearDown(self):
        self.srv.close()
        super().tearDown()

    def test_brief_format_and_privacy(self):
        text, info = report.brief(self.kb, "t1")
        self.assertIn("## TL;DR\nL0: FSRS is a three-variable memory model.", text)
        self.assertIn(f"{{S:{self.pub}}}", text)                      # create-report evidence tags, same ids
        self.assertIn(f"- {self.pub}: ", text)                        # Sources line in create-report format
        self.assertNotIn(self.priv, text)                             # private source left out
        self.assertNotIn("studies irregularly", text)                 # claim resting only on it dropped
        self.assertNotIn("kanji", text)                               # the user's own question: never
        self.assertNotIn("forgetting at work", text)                  # annotations: never
        self.assertNotIn("six years", text)                           # personal context: never
        self.assertEqual((info["excluded_sources"], info["dropped_claims"]), (1, 1))

    def test_guard_detects_leaks(self):
        site = self.tmp / "report-site"
        site.mkdir()
        (site / "index.html").write_text("<html><body><p>FSRS has three memory variables.</p></body></html>")
        self.assertEqual(report.guard(self.kb, str(site)), [])
        (site / "index.html").write_text("<p>Note: this reminds me of my own <b>forgetting</b> at work.</p>"
                                         "<li>My private study diary</li>")
        probs = report.guard(self.kb, str(site))
        self.assertTrue(any("annotation" in p for p in probs))
        self.assertTrue(any("private source title" in p for p in probs))
        (site / "state.json").write_text("{}")
        self.assertTrue(any("learning-state file" in p for p in report.guard(self.kb, str(site))))

    def test_private_paths_refused(self):
        with self.assertRaises(KwError):
            report.write_brief(self.kb, str(self.www / "x" / "brief.md"), "x")
        os.environ["KW_HOME"] = str(self.www / "kb-inside-www")
        try:
            with self.assertRaises(KwError):
                Paths().check_private_location()
        finally:
            os.environ["KW_HOME"] = str(self.home)

    def test_ordinary_operations_never_touch_www(self):
        """Run every user-facing operation and check the public web root stays empty."""
        report.write_brief(self.kb, str(self.tmp / "reports" / "x" / "brief.md"), report.brief(self.kb, "t1")[0])
        export.obsidian(self.kb, highlights=["all"], concepts=["stability"])
        self.kw("dossier", "t1")
        self.kw("consolidate", "t1", "--apply-safe")
        self.kw("run", "begin", "--topic", "t1")
        self.kw("run", "end", "--topic", "t1", "--summary", "s", "--stop-reason", "done")
        self.kw("learn", "session", "--minutes", "10")
        from kinwing import reader
        api = reader.Api(self.kb)
        api.home(); api.topic("t1"); api.concept("stability"); api.source(self.pub)
        self.assertEqual(list(self.www.rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
