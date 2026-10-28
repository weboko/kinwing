"""Research runs: cumulative state, budgets, stopping conditions, crash recovery."""

import datetime as dt
import unittest

from tests.util import DOC, KwTestCase
from kinwing import notify, runs
from kinwing.store import KwError


def ago(minutes):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


class RunTest(KwTestCase):
    def setUp(self):
        super().setUp()
        self.topic(budget={"max_questions_per_run": 2, "max_sources_per_run": 2, "max_minutes": 30, "max_runs_per_week": 3})
        self.q = [self.kb.add_question("t1", f"Question {i}?", priority=p)
                  for i, p in enumerate(["high", "medium", "low"])]

    def _research(self, rid, text=DOC, name="doc.md"):
        """What an agent does during a run, via the same code paths as the CLI."""
        from kinwing import ingest
        s = ingest.add_source(self.kb, "t1", file=str(self.write(name, text)), run=rid)
        if s["_status"] == "added":
            e = self.kb.add_evidence(s["id"], "FSRS models memory with three components", "t1", run=rid)
            self.kb.add_claim("t1", "FSRS has three memory components", support=[e["id"]], run=rid)
        return s

    def test_begin_selects_top_questions_and_end_records(self):
        meta, brief = runs.begin(self.kb, "t1", agent="test")
        self.assertEqual(meta["questions_selected"], [self.q[0]["id"], self.q[1]["id"]])
        self.assertEqual(self.kb.load("question", self.q[0]["id"])[0]["status"], "in_progress")
        self.assertIn("Questions selected for this run", brief)
        self._research(meta["id"])
        self.kb.update_question(self.q[0]["id"], status="answered", result="yes", run=meta["id"])
        done = runs.end(self.kb, meta["id"], "did things", "budget")
        self.assertEqual(done["stats"]["sources_added"], 1)
        self.assertEqual(done["stats"]["claims_added"], 1)
        self.assertEqual(done["stats"]["questions_answered"], 1)
        # the unfinished selected question goes back to the queue
        self.assertEqual(self.kb.load("question", self.q[1]["id"])[0]["status"], "open")
        self.assertIsNotNone(self.kb.topic("t1")["last_investigated"])
        self.assertTrue((self.p.topic_dir("t1") / "dossier.md").exists())

    def test_second_run_builds_on_the_first(self):
        r1, _ = runs.begin(self.kb, "t1")
        self._research(r1["id"])
        self.kb.update_question(self.q[0]["id"], status="answered", result="yes", run=r1["id"])
        runs.end(self.kb, r1["id"], "first", "done", next_steps=["look at SM-2"])
        r2, brief = runs.begin(self.kb, "t1")
        self.assertNotIn(self.q[0]["id"], r2["questions_selected"])  # answered: not picked again
        self.assertIn("look at SM-2", brief)                        # previous run's advice is carried
        self.assertIn("FSRS has three memory components", brief)    # known conclusions are shown
        s = self._research(r2["id"], name="same.md")                 # the same material again
        self.assertEqual(s["_status"], "known-content")
        out = runs.end(self.kb, r2["id"], "second", "done")
        self.assertEqual((out["stats"]["sources_added"], out["stats"]["claims_added"]), (0, 0))
        self.assertEqual(len(self.kb.metas("source")), 1)
        self.assertEqual(len(self.kb.metas("claim")), 1)

    def test_source_budget_enforced(self):
        r, _ = runs.begin(self.kb, "t1")
        self._research(r["id"], text=DOC + "a", name="a.md")
        self._research(r["id"], text=DOC + "b", name="b.md")
        with self.assertRaises(KwError) as cm:
            self._research(r["id"], text=DOC + "c", name="c.md")
        self.assertEqual(cm.exception.code, runs.EXIT_SOURCES)

    def test_deadline_enforced(self):
        r, _ = runs.begin(self.kb, "t1")
        m, b = self.kb.load("run", r["id"])
        m["deadline"] = ago(1)
        self.kb.save("run", m, b)
        with self.assertRaises(KwError) as cm:
            self._research(r["id"])
        self.assertEqual(cm.exception.code, runs.EXIT_DEADLINE)
        self.assertIn("past its deadline", runs.deadline_note(self.kb, r["id"]))

    def test_paused_topic_refuses(self):
        self.kb.set_topic_fields("t1", {"status": "paused"})
        with self.assertRaises(KwError) as cm:
            runs.begin(self.kb, "t1")
        self.assertEqual(cm.exception.code, runs.EXIT_PAUSED)

    def test_weekly_limit(self):
        for _ in range(3):
            r, _ = runs.begin(self.kb, "t1")
            runs.end(self.kb, r["id"], "x", "done")
        with self.assertRaises(KwError) as cm:
            runs.begin(self.kb, "t1")
        self.assertEqual(cm.exception.code, runs.EXIT_WEEKLY)

    def test_one_active_run_per_topic(self):
        runs.begin(self.kb, "t1")
        with self.assertRaises(KwError) as cm:
            runs.begin(self.kb, "t1")
        self.assertEqual(cm.exception.code, runs.EXIT_BUSY)

    def test_interrupted_run_is_recovered(self):
        r, _ = runs.begin(self.kb, "t1")
        self._research(r["id"])  # it got some work done, then the box restarted
        m, b = self.kb.load("run", r["id"])
        m["started"] = ago(200)
        self.kb.save("run", m, b)
        r2, brief = runs.begin(self.kb, "t1")
        old = self.kb.load("run", r["id"])[0]
        self.assertEqual(old["status"], "interrupted")
        self.assertEqual(old["stats"]["claims_added"], 1)   # its work is kept
        self.assertIn(r["id"], r2["recovered_runs"])
        self.assertIn("Recovered interrupted run", brief)
        # its questions were released and re-selected by the new run
        self.assertEqual(r2["questions_selected"], r["questions_selected"])
        self.assertEqual(len(self.kb.metas("claim")), 1)

    def test_low_yield_twice_notifies(self):
        for _ in range(2):
            r, _ = runs.begin(self.kb, "t1")
            out = runs.end(self.kb, r["id"], "nothing found", "exhausted")
            self.assertTrue(out["low_yield"])
        msgs = [n["message"] for n in notify.items(self.p)]
        self.assertTrue(any("added nothing new" in m for m in msgs))

    def test_usage_from_orchestrator_log(self):
        d = self.tmp / "ao-run"
        d.mkdir()
        (d / "agent.log").write_text('{"type":"system"}\n{"type":"result","total_cost_usd":1.5,"num_turns":12,'
                                     '"duration_ms":90000,"usage":{"input_tokens":10,"output_tokens":2000}}\n')
        (d / "exit_code").write_text("0\n")
        r, _ = runs.begin(self.kb, "t1", ao_run_dir=str(d))
        runs.end(self.kb, r["id"], "x", "done")
        runs.sync_usage(self.kb)
        u = self.kb.load("run", r["id"])[0]["usage"]
        self.assertEqual((u["total_cost_usd"], u["num_turns"], u["output_tokens"]), (1.5, 12, 2000))

    def test_cli_run_flow(self):
        code, out = self.kw("run", "begin", "--topic", "t1")
        self.assertIn("Research run", out)
        self.kw("source", "add", "--topic", "t1", "--file", str(self.write("d.md", DOC)))  # picks the active run up
        rid = runs.current_run(self.kb, "t1")
        self.assertEqual(self.kb.metas("source")[0]["added_by_run"], rid)
        code, out = self.kw("run", "end", "--topic", "t1", "--summary", "s", "--stop-reason", "done", "--continue", "no")
        self.assertIn("completed", out)
        self.assertTrue(any("recommends no further runs" in n["message"] for n in notify.items(self.p)))


if __name__ == "__main__":
    unittest.main()
