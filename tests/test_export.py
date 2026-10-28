"""Obsidian export: valid Markdown + frontmatter, quotes vs AI text vs own words, safety."""

import unittest

from tests.util import DOC, KwTestCase
from kinwing import export, yamlio
from kinwing.learning import Learning
from kinwing.store import KwError


class ExportTest(KwTestCase):
    def setUp(self):
        super().setUp()
        self.topic(title="Spaced repetition")
        self.sid = self.source_from_text(DOC, rights="open", summary="A short note on two models.")["id"]
        e = self.kb.add_evidence(self.sid, "Stability is the time, in days, for retrievability to fall from 100% to 90%.", "t1")
        self.kb.add_concept("t1", "Memory stability", cid="stability", summary="How long a memory lasts.",
                            explanation="Stability is measured in days; see [[retrievability]].", related="retrievability:contrasts")
        self.kb.add_concept("t1", "Retrievability", cid="retrievability", summary="Recall odds now.")
        self.kb.add_claim("t1", "Stability is defined at the 90% recall point", support=[e["id"]], concepts="stability",
                          strength="strong")
        L = Learning(self.kb)
        self.h = L.add_highlight("source", self.sid, "for retrievability to fall from 100% to 90%",
                                 note="So it is a 90%-life, not a half-life.")
        L.add_answer("stability", "What is it?", "Days until I'd only have a 90% chance to recall.")
        self.out = self.tmp / "vault-export"

    def _note(self, rel):
        meta, body = yamlio.split_frontmatter((self.out / rel).read_text())
        return meta, body

    def test_source_and_concept_notes(self):
        res = export.obsidian(self.kb, highlights=[self.h["id"]], concepts=["stability"], out=str(self.out))
        paths = {f["path"].split("vault-export/")[1] for f in res["files"]}
        self.assertIn("Sources/Memory models.md", paths)
        self.assertIn("Concepts/Memory stability.md", paths)
        self.assertIn("Topics/Spaced repetition.md", paths)
        meta, body = self._note("Sources/Memory models.md")
        self.assertEqual(meta["kw_id"], f"source:{self.sid}")
        self.assertIn("kinwing/source", meta["tags"])
        self.assertEqual(meta["topics"], ["[[Spaced repetition]]"])
        self.assertIn("> for retrievability to fall from 100% to 90%", body)          # exact quote as a quotation
        self.assertIn(f"^{self.h['id']}", body)                                       # stable block id
        self.assertIn("**My note:** So it is a 90%-life", body)                       # own words, labelled
        self.assertIn("Written by an AI research agent", body)                        # AI summary, labelled
        cmeta, cbody = self._note("Concepts/Memory stability.md")
        self.assertEqual(cmeta["kw_type"], "concept-note")
        self.assertEqual(cmeta["sources"], ["[[Memory models]]"])
        self.assertLess(cbody.index("## My thoughts"), cbody.index("## AI synthesis"))
        self.assertIn("Days until I'd only have a 90% chance", cbody)
        self.assertIn("“Stability is the time, in days, for retrievability to fall from 100% to 90%.” — [[Memory models]]", cbody)
        self.assertNotIn("[[retrievability]]", cbody)  # kinwing ids are not left as dangling vault links

    def test_curated_not_bulk(self):
        res = export.obsidian(self.kb, highlights=[self.h["id"]], out=str(self.out))
        self.assertFalse((self.out / "Concepts").exists())  # no concept notes unless asked for
        with self.assertRaises(KwError):
            export.obsidian(self.kb, out=str(self.out))

    def test_user_edits_are_not_overwritten(self):
        export.obsidian(self.kb, highlights=[self.h["id"]], out=str(self.out))
        note = self.out / "Sources" / "Memory models.md"
        note.write_text(note.read_text() + "\nMy own addition in Obsidian.\n")
        Learning(self.kb).update_highlight(self.h["id"], note="Updated note.")
        res = export.obsidian(self.kb, highlights=[self.h["id"]], out=str(self.out))
        kept = [f for f in res["files"] if f["path"].endswith("Memory models.md")][0]
        self.assertEqual(kept["action"], "kept")
        self.assertIn("My own addition in Obsidian.", note.read_text())
        self.assertTrue((self.out / ".kinwing" / "pending" / "Memory models.md").exists())
        res = export.obsidian(self.kb, highlights=[self.h["id"]], out=str(self.out), force=True)
        self.assertIn("Updated note.", note.read_text())

    def test_reexport_is_idempotent(self):
        export.obsidian(self.kb, highlights=["all"], concepts=["stability"], out=str(self.out))
        res = export.obsidian(self.kb, highlights=["all"], concepts=["stability"], out=str(self.out))
        self.assertEqual({f["action"] for f in res["files"]}, {"unchanged"})

    def test_refuses_public_web_root(self):
        with self.assertRaises(KwError):
            export.obsidian(self.kb, highlights=["all"], out=str(self.www / "notes"))


if __name__ == "__main__":
    unittest.main()
