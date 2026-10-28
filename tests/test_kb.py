"""Topics, identifiers, the question queue, evidence and claims."""

import unittest

from tests.util import DOC, KwTestCase
from kinwing import store
from kinwing.store import KwError


class TopicTest(KwTestCase):
    def test_create_and_load_config(self):
        self.kw("topic", "new", "--title", "Economics of decentralized messaging", "--objective", "understand incentives",
                "--familiarity", "knows the protocols", "--depth", "deep", "--exclude", "cryptography basics",
                "--perspective", "econ:Economics:who pays", "--max-sources", "5")
        t = self.kb.topic("economics-of-decentralized-messaging")
        self.assertEqual(t["depth"], "deep")
        self.assertEqual(t["familiarity"], "knows the protocols")
        self.assertEqual(t["boundaries"]["exclude"], ["cryptography basics"])
        self.assertEqual(t["perspectives"][0]["id"], "econ")
        self.assertEqual(t["budget"]["max_sources_per_run"], 5)
        self.assertEqual(t["budget"]["max_minutes"], 40)  # default filled in
        self.assertTrue((self.p.topic_dir(t["id"]) / "overview.md").exists())

    def test_stable_id_and_refuse_duplicate(self):
        t = self.topic("my-topic", title="Original title")
        self.kb.set_topic_fields("my-topic", {"title": "Renamed"})
        self.assertEqual(self.kb.topic("my-topic")["id"], "my-topic")  # rename never changes the id
        with self.assertRaises(KwError):
            self.topic("my-topic")
        with self.assertRaises(KwError):
            self.kb.create_topic("x", tid="Bad Id!")

    def test_set_validates(self):
        self.topic()
        self.kw("topic", "set", "t1", "depth=monitor", "budget.max_minutes=15", "exclude_x=1")
        t = self.kb.topic("t1")
        self.assertEqual((t["depth"], t["budget"]["max_minutes"]), ("monitor", 15))
        code, out = self.kw("topic", "set", "t1", "depth=forever", ok=False)
        self.assertNotEqual(code, 0)

    def test_hand_edited_topic_yaml_is_read(self):
        self.topic()
        f = self.p.topic_dir("t1") / "topic.yaml"
        f.write_text(f.read_text().replace("depth: orientation", "depth: deep  # changed by hand"))
        self.assertEqual(self.kb.topic("t1")["depth"], "deep")


class QuestionTest(KwTestCase):
    def test_queue_persists_and_ranks(self):
        self.topic()
        a = self.kb.add_question("t1", "Low value question?", priority="low", value="low")
        b = self.kb.add_question("t1", "What does the user care about?", origin="user", priority="high", value="high")
        c = self.kb.add_question("t1", "Depends on b?", depends_on=[b["id"]], priority="high")
        ranked = [q["id"] for s, w, q in self.kb.ranked_questions("t1") if s >= 0]
        self.assertEqual(ranked[0], b["id"])
        self.assertNotIn(c["id"], ranked)  # blocked by an unanswered dependency
        self.kb.update_question(b["id"], status="answered", result="it's this")
        ranked = [q["id"] for s, w, q in self.kb.ranked_questions("t1") if s >= 0]
        self.assertIn(c["id"], ranked)
        # Persistence: a fresh KB object reads the same state from disk.
        from kinwing.kb import KB
        q = KB(store.Paths()).load("question", b["id"])[0]
        self.assertEqual((q["status"], q["result"]), ("answered", "it's this"))
        self.assertIn("status open → answered", KB(store.Paths()).load("question", b["id"])[1])

    def test_duplicate_question_not_added(self):
        self.topic()
        a = self.kb.add_question("t1", "Why did X fail?")
        b = self.kb.add_question("t1", "why did   x fail")
        self.assertEqual(a["id"], b["id"])
        self.assertTrue(b.get("_duplicate"))
        self.assertEqual(len(self.kb.metas("question", "t1")), 1)

    def test_id_format(self):
        self.topic()
        q = self.kb.add_question("t1", "Q?")
        self.assertRegex(q["id"], r"^q-\d{8}-[a-z2-9]{4}$")


class EvidenceClaimTest(KwTestCase):
    def setUp(self):
        super().setUp()
        self.topic()
        self.src = self.source_from_text(DOC)["id"]

    def test_evidence_links_to_source_and_verifies_quote(self):
        e = self.kb.add_evidence(self.src, "Stability is the time, in days, for retrievability to fall from 100% to 90%.", "t1")
        self.assertTrue(e["quote_verified"])
        self.assertEqual(e["source"], self.src)
        self.assertEqual(e["locator"], "¶3")
        # typographic quotes / whitespace differences still verify
        e2 = self.kb.add_evidence(self.src, "SM-2   uses an ease factor that starts at 2.5", "t1")
        self.assertTrue(e2["quote_verified"])
        with self.assertRaises(KwError):
            self.kb.add_evidence(self.src, "a sentence the source never says at all", "t1")
        e3 = self.kb.add_evidence(self.src, "a paraphrase from a page section not stored", "t1", allow_unverified=True)
        self.assertFalse(e3["quote_verified"])
        self.assertIn(("warn", f"{e3['id']}: quote not verified against the stored source text"), self.kb.check())

    def test_finding_needs_evidence(self):
        with self.assertRaises(KwError):
            self.kb.add_claim("t1", "Unsupported finding", kind="finding")
        h = self.kb.add_claim("t1", "A hunch", kind="hypothesis", strength="moderate")
        self.assertEqual(h["strength"], "unsupported")  # no evidence -> can't be 'moderate'

    def test_conflicting_evidence_is_preserved(self):
        e1 = self.kb.add_evidence(self.src, "SM-2 uses an ease factor that starts at 2.5 for every card.", "t1")
        e2 = self.kb.add_evidence(self.src, "FSRS models memory with three components", "t1")
        c1 = self.kb.add_claim("t1", "SM-2 starts every card at the same ease", support=[e1["id"]], strength="strong")
        c2 = self.kb.add_claim("t1", "SM-2 personalises the starting ease per card", support=[e2["id"]],
                               strength="moderate", contradicts=[c1["id"]])
        m1, b1 = self.kb.load("claim", c1["id"])
        m2, _ = self.kb.load("claim", c2["id"])
        # both kept, both contested, linked both ways, the original text untouched
        self.assertEqual((m1["strength"], m2["strength"]), ("contested", "contested"))
        self.assertEqual(m1["text"], "SM-2 starts every card at the same ease")
        self.assertIn(c2["id"], m1["contradicts"])
        self.assertIn("contradicted by", b1)
        self.assertEqual(m1["support"], [e1["id"]])

    def test_revision_requires_reason_and_is_logged(self):
        e1 = self.kb.add_evidence(self.src, "FSRS models memory with three components", "t1")
        c = self.kb.add_claim("t1", "FSRS has three memory variables", support=[e1["id"]], strength="moderate")
        with self.assertRaises(KwError):
            self.kb.update_claim(c["id"], reason="", strength="strong")
        self.kb.update_claim(c["id"], reason="second source agrees", strength="strong", run="run-x")
        meta, body = self.kb.load("claim", c["id"])
        self.assertEqual(meta["strength"], "strong")
        self.assertIn("strength moderate → strong — second source agrees", body)
        self.assertTrue(any(ch.get("detail", "").endswith("second source agrees") for ch in self.kb.changes("t1")))

    def test_supersede_keeps_history(self):
        e1 = self.kb.add_evidence(self.src, "FSRS models memory with three components", "t1")
        old = self.kb.add_claim("t1", "FSRS has two variables", support=[e1["id"]], strength="weak")
        new = self.kb.add_claim("t1", "FSRS has three variables", support=[e1["id"]], strength="strong")
        self.kb.supersede_claim(old["id"], new["id"], "misread the source")
        om, ob = self.kb.load("claim", old["id"])
        self.assertEqual((om["state"], om["superseded_by"]), ("superseded", new["id"]))
        self.assertIn("misread the source", ob)
        self.assertTrue(self.p.entity_path("claim", old["id"]).exists())  # never deleted
        with self.assertRaises(KwError):
            self.kb.update_claim(old["id"], reason="x", strength="strong")

    def test_check_finds_broken_references(self):
        e1 = self.kb.add_evidence(self.src, "FSRS models memory with three components", "t1")
        self.kb.add_claim("t1", "FSRS has three variables", support=[e1["id"]])
        self.p.entity_path("evidence", e1["id"]).unlink()
        errors = [m for lvl, m in self.kb.check() if lvl == "error"]
        self.assertTrue(any(e1["id"] in m for m in errors))


class ConceptTest(KwTestCase):
    def test_concept_sections_and_versions(self):
        self.topic()
        self.kb.add_concept("t1", "Memory stability", cid="stability", summary="How long a memory lasts.",
                            explanation="First explanation.", prompts=["explain:What is it?", "free text prompt"])
        meta, secs = self.kb.concept_sections("stability")
        self.assertEqual(secs["Explanation"], "First explanation.")
        self.assertIn("**explain**: What is it?", secs["Prompts"])
        self.kb.update_concept("stability", explanation="Better explanation.", alternative="Think of a half-life.")
        meta, secs = self.kb.concept_sections("stability")
        self.assertEqual(secs["Explanation"], "Better explanation.")
        self.assertIn("First explanation.", secs["Previous versions"])  # old text kept
        self.assertEqual(secs["Alternative explanation"], "Think of a half-life.")

    def test_concepts_span_topics(self):
        self.topic("a")
        self.topic("b")
        self.kb.add_concept("a", "Network effects", cid="network-effects", summary="x")
        again = self.kb.add_concept("b", "Network effects", cid="network-effects")
        self.assertTrue(again["_duplicate"])
        self.assertEqual(self.kb.load("concept", "network-effects")[0]["topics"], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
