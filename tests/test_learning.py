"""Personal learning state: separate from the kb, observed vs self-reported vs inferred."""

import json
import unittest

from tests.util import DOC, KwTestCase
from kinwing.learning import Learning
from kinwing.store import KwError


class LearningTest(KwTestCase):
    def setUp(self):
        super().setUp()
        self.topic()
        self.kb.add_concept("t1", "Stability", cid="stability", summary="How long a memory lasts.",
                            explanation="Stability is measured in days.", prompts=["explain:What is it?"])
        self.kb.add_concept("t1", "Retrievability", cid="retrievability", summary="Recall odds now.",
                            prerequisites=["stability"])
        self.L = Learning(self.kb)

    def test_progress_persists_and_resumes(self):
        self.L.record_progress("concept", "stability", fraction=0.4, para=3, depth="read", seconds=30, view=True)
        st = Learning(self.kb).state()  # a new process reads it back from disk
        o = st["concepts"]["stability"]["observed"]
        self.assertEqual((o["progress"], o["para"], o["views"], o["depth_max"]), (0.4, 3, 1, "read"))
        self.assertEqual(st["last_position"]["id"], "stability")
        self.L.record_progress("concept", "stability", fraction=0.2)
        self.assertEqual(self.L.state()["concepts"]["stability"]["observed"]["progress"], 0.4)  # max, not last
        # learning state lives outside the kb
        self.assertTrue((self.p.learning / "state.json").exists())
        self.assertFalse(any("state.json" in str(f) for f in self.p.kb.rglob("*")))

    def test_viewing_is_not_understanding(self):
        self.L.record_progress("concept", "stability", fraction=1.0, view=True, completed=True, depth="deep")
        inf = self.L.infer("stability")
        self.assertEqual(inf["status"], "read")
        self.assertNotIn("master", inf["status"])
        self.L.add_answer("stability", "What is it?", "The days until recall odds drop to 90%.")
        self.assertEqual(self.L.infer("stability")["status"], "practised")
        a = self.L.answers(pending=True)[0]
        self.L.review_answer(a["id"], "sound", "correct and in own words")
        self.assertEqual(self.L.infer("stability")["status"], "shows understanding")
        self.assertIn("reviewed sound", self.L.infer("stability")["basis"])

    def test_known_concepts_stop_being_suggested(self):
        recs = [r["concept"] for r in self.L.recommend("t1")]
        self.assertIn("stability", recs)
        self.L.self_report("stability", "known")
        recs = [r["concept"] for r in self.L.recommend("t1")]
        self.assertNotIn("stability", recs)
        self.assertEqual(self.L.infer("stability")["status"], "self-reported known")

    def test_prerequisites_and_confusion_shape_suggestions(self):
        r = {x["concept"]: x for x in self.L.recommend("t1")}
        self.assertTrue(any("builds on stability" in why for why in r["retrievability"]["reasons"]))
        self.assertGreater(r["stability"]["score"], r["retrievability"]["score"])
        self.L.self_report("retrievability", "confused")
        r = {x["concept"]: x for x in self.L.recommend("t1")}
        self.assertTrue(any("confusing" in why for why in r["retrievability"]["reasons"]))
        self.assertTrue(self.L.state()["concepts"]["retrievability"]["revisit"]["due"])

    def test_questions_feed_the_research_queue(self):
        q = self.L.ask("challenge", "Why 90% and not 50%?", concept="stability", quote="measured in days")
        meta = self.kb.load("question", q["id"])[0]
        self.assertEqual((meta["origin"], meta["asked_by"], meta["topic"]), ("learning", "user", "t1"))
        self.assertEqual(meta["concepts"], ["stability"])
        self.assertIn("not convinced", meta["text"])
        self.assertIn("measured in days", meta["context"])
        top = self.kb.ranked_questions("t1")[0][2]
        self.assertEqual(top["id"], q["id"])  # user doubts get priority
        self.assertEqual([x["id"] for x in self.L.my_questions()], [q["id"]])

    def test_highlights_distinguish_source_quotes(self):
        sid = self.source_from_text(DOC)["id"]
        h1 = self.L.add_highlight("source", sid, "for retrievability to fall from 100% to 90%", note="My take.")
        self.assertEqual((h1["quote_origin"], h1["locator"]), ("source text (exact)", "¶3"))
        h2 = self.L.add_highlight("concept", "stability", "measured in days")
        self.assertEqual(h2["quote_origin"], "AI-written synthesis")
        self.L.update_highlight(h1["id"], note="Changed my mind.")
        hs = {h["id"]: h for h in self.L.highlights()}
        self.assertEqual(hs[h1["id"]]["note"], "Changed my mind.")
        self.L.delete_highlight(h2["id"])
        self.assertNotIn(h2["id"], {h["id"] for h in self.L.highlights()})
        with self.assertRaises(KwError):
            self.L.add_highlight("concept", "nope", "text")

    def test_session_and_changes_since_visit(self):
        s = self.L.create_session(minutes=10, topic="t1")
        self.assertTrue(s["items"])
        self.L.session_step(s["id"], 0)
        self.assertTrue(self.L.session(s["id"])["items"][0]["done"])
        since, ch = self.L.changes_since_visit("t1")
        self.assertIsNone(since)
        self.assertTrue(ch)
        self.L.visit_topic("t1")
        self.assertEqual(self.L.changes_since_visit("t1")[1], [])
        self.kb.add_question("t1", "A new question after the visit?")
        self.assertEqual(len(self.L.changes_since_visit("t1")[1]), 1)


if __name__ == "__main__":
    unittest.main()
