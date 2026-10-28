"""Dossier generation and consolidation."""

import unittest

from tests.util import DOC, KwTestCase
from kinwing import consolidate, dossier


class SynthesisTest(KwTestCase):
    def setUp(self):
        super().setUp()
        self.topic(perspectives=[{"id": "algo", "name": "Algorithm", "why": ""}, {"id": "ux", "name": "Usability", "why": ""}])
        self.src = self.source_from_text(DOC)["id"]
        self.e1 = self.kb.add_evidence(self.src, "FSRS models memory with three components", "t1")["id"]
        self.e2 = self.kb.add_evidence(self.src, "SM-2 uses an ease factor that starts at 2.5", "t1")["id"]

    def test_dossier_sections_and_updates(self):
        c = self.kb.add_claim("t1", "FSRS uses three memory variables", support=[self.e1], strength="strong")
        self.kb.add_question("t1", "How is difficulty estimated?", perspective="algo")
        (self.p.topic_dir("t1") / "overview.md").write_text("# T\n\nFSRS is a model of memory.\n")
        text = dossier.build(self.kb, "t1")
        for heading in ["## 1. Orientation", "## 2. Main concepts", "## 3. Current conclusions", "## 4. Supporting evidence",
                        "## 5. Competing explanations", "## 6. Important uncertainties", "## 7. Research questions",
                        "## 8. Recommended next investigations", "## 9. Sources", "## 10. Recent changes"]:
            self.assertIn(heading, text)
        self.assertIn("FSRS is a model of memory.", text)
        self.assertIn(f"../../claims/{c['id']}.md", text)                 # navigable provenance
        self.assertIn(f"../../evidence/{self.e1}.md", text)
        self.assertIn("Perspectives without questions yet: Usability", text)
        self.kb.update_claim(c["id"], reason="a second source contradicts the count", strength="weak")
        text2 = dossier.build(self.kb, "t1")
        self.assertIn("### Weak", text2)
        self.assertIn("a second source contradicts the count", text2)    # the why of the change is visible
        self.assertTrue((self.p.topic_dir("t1") / "changes.md").exists())
        self.assertIn("Test topic", (self.p.kb / "README.md").read_text())

    def test_consolidation_finds_and_merges_duplicates(self):
        a = self.kb.add_claim("t1", "FSRS models memory using three components", support=[self.e1])
        b = self.kb.add_claim("t1", "FSRS models memory with three distinct components", support=[self.e1])
        res, report, _ = consolidate.run(self.kb, "t1")
        self.assertEqual(len(res["duplicates"]), 1)
        self.assertTrue(f"kw claim merge {a['id']} {b['id']}" in report or f"kw claim merge {b['id']} {a['id']}" in report)
        self.kb.merge_claims(a["id"], b["id"], "same claim")
        self.assertEqual(self.kb.load("claim", b["id"])[0]["state"], "superseded")
        self.assertEqual(consolidate.analyze(self.kb, "t1")["duplicates"], [])
        self.assertTrue((self.p.topic_dir("t1") / "consolidation.md").exists())

    def test_consolidation_conflicts_and_safe_apply(self):
        a = self.kb.add_claim("t1", "SM-2 starting ease is fixed at 2.5", support=[self.e2], strength="strong")
        b = self.kb.add_claim("t1", "SM-2 starting ease is not fixed at 2.5", kind="hypothesis", strength="weak")
        res = consolidate.analyze(self.kb, "t1")
        self.assertEqual(len(res["conflicts"]), 1)                         # opposite polarity detected
        self.kb.update_claim(a["id"], reason="counter source", add_counter=[self.e1])
        res, _, applied = consolidate.run(self.kb, "t1", apply_safe=True)
        self.assertEqual(self.kb.load("claim", a["id"])[0]["strength"], "contested")
        self.assertTrue(applied)
        self.assertTrue(self.p.entity_path("claim", b["id"]).exists())     # nothing deleted

    def test_orphan_and_unsupported(self):
        res = consolidate.analyze(self.kb, "t1")
        self.assertEqual({e["id"] for e in res["orphan_evidence"]}, {self.e1, self.e2})


if __name__ == "__main__":
    unittest.main()
