"""Recurring research through ai-box's real agent-orchestrator scripts.

Needs a checkout of weboko/ai-box: set AIBOX_DIR (the demo and Docker test runner do).
The agent is tests/fakes/claude and the crontab is tests/fakes/crontab, so nothing on the
machine is changed and no LLM is called."""

import json
import os
import re
import shutil
import subprocess
import time
import unittest
from pathlib import Path

from tests.util import ROOT, KwTestCase
from kinwing import runs

AIBOX = os.environ.get("AIBOX_DIR", "")
AO_SRC = Path(AIBOX) / "context" / "skills" / "agent-orchestrator"


@unittest.skipUnless(AIBOX and (AO_SRC / "bin" / "schedule.sh").exists(), "set AIBOX_DIR to a weboko/ai-box checkout")
class ScheduleTest(KwTestCase):
    def setUp(self):
        super().setUp()
        self.ao_home = self.tmp / "ao"
        self.saved = {k: os.environ.get(k) for k in ("AO_HOME", "KW_AO_BIN", "PATH", "FAKE_CRONTAB", "FAKE_AGENT_SLEEP",
                                                     "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")}
        os.environ.update({"AO_HOME": str(self.ao_home), "KW_AO_BIN": str(AO_SRC / "bin"),
                           "PATH": f"{ROOT / 'tests' / 'fakes'}:{os.environ['PATH']}",
                           "FAKE_CRONTAB": str(self.tmp / "crontab.txt"),
                           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})
        self.topic(budget={"max_runs_per_week": 3})
        self.kb.add_question("t1", "First question?")

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        super().tearDown()

    def cron_command(self):
        line = [l for l in Path(os.environ["FAKE_CRONTAB"]).read_text().splitlines() if "run-scheduled.sh" in l][0]
        return line.split(None, 5)[5]  # drop the 5 schedule fields

    def fire(self):
        subprocess.run(["bash", "-c", self.cron_command()], check=True)

    def wait_runs(self, n, timeout=30):
        t0 = time.time()
        while time.time() - t0 < timeout:
            done = [d for d in (self.ao_home / "runs").glob("*/run.json") if json.loads(d.read_text())["status"] != "running"]
            if len(done) >= n:
                return
            time.sleep(0.3)
        self.fail("orchestrator run did not finish")

    def test_schedule_fire_inspect_pause_resume(self):
        code, out = self.kw("schedule", "add", "t1", "--cron", "0 9 * * 1,3,5", "--agent", "claude", "--max-duration", "45m")
        spec = self.ao_home / "scheduled" / "kw-t1.md"
        text = spec.read_text()
        self.assertIn('mode: "local"', text)
        self.assertIn(f'workdir: "{self.p.kb}"', text)
        self.assertIn('max_duration: "45m"', text)
        self.assertIn("{{RUN_DIR}}", text)
        self.assertIn("0 9 * * 1,3,5", Path(os.environ["FAKE_CRONTAB"]).read_text())
        self.assertTrue(self.kb.topic("t1")["schedule"]["enabled"])

        self.fire()                          # cron fires once
        self.wait_runs(1)
        ao_run = json.loads(next((self.ao_home / "runs").glob("*/run.json")).read_text())
        self.assertEqual(ao_run["status"], "done")
        self.assertEqual(ao_run["workdir"], str(self.p.kb))
        kr = [r for r in self.kb.metas("run") if r.get("status") == "completed"]
        self.assertEqual(len(kr), 1)
        runs.sync_usage(self.kb)
        self.assertEqual(self.kb.load("run", kr[0]["id"])[0]["usage"]["num_turns"], 3)
        log = subprocess.run(["git", "-C", str(self.p.kb), "log", "--oneline"], capture_output=True, text=True).stdout
        self.assertIn("t1: fake run", log)   # the kb history records the run

        os.environ["FAKE_AGENT_SLEEP"] = "4"  # a slow run, then a second firing while it is alive
        self.fire()
        time.sleep(1)
        self.fire()
        cron_log = (self.ao_home / "runs" / "cron.kw-t1.log").read_text()
        self.assertIn("reason=previous-run-alive", cron_log)
        self.wait_runs(2)
        os.environ.pop("FAKE_AGENT_SLEEP")
        self.assertEqual(len([r for r in self.kb.metas("run") if r.get("status") == "completed"]), 2)

        self.kw("schedule", "pause", "t1")
        self.assertIn('status: "stopped"', spec.read_text())
        self.assertNotIn("run-scheduled.sh", Path(os.environ["FAKE_CRONTAB"]).read_text())
        subprocess.run([str(AO_SRC / "bin" / "run-scheduled.sh"), str(spec)], capture_output=True)
        self.kw("schedule", "resume", "t1")
        self.assertIn('status: "active"', spec.read_text())
        code, out = self.kw("schedule", "list")
        self.assertIn("kw-t1", out)

    def test_paused_topic_and_weekly_budget_stop_the_agent(self):
        self.kw("schedule", "add", "t1", "--cron", "0 9 * * *")
        self.kw("topic", "pause", "t1")      # also disables the schedule
        self.assertIn('status: "stopped"', (self.ao_home / "scheduled" / "kw-t1.md").read_text())
        # Even a manual launch can't run research on a paused topic: kw refuses and the agent stops.
        subprocess.run([str(AO_SRC / "bin" / "run-task.sh"), "--task", str(self.ao_home / "scheduled" / "kw-t1.md")],
                       check=True, capture_output=True)
        self.wait_runs(1)
        report = next((self.ao_home / "runs").glob("*/report.md")).read_text()
        self.assertIn("exit code: 10", report)
        self.assertEqual(self.kb.metas("run"), [])
        self.kw("topic", "resume", "t1")
        for _ in range(3):
            r, _ = runs.begin(self.kb, "t1")
            runs.end(self.kb, r["id"], "x", "done")
        subprocess.run([str(AO_SRC / "bin" / "run-task.sh"), "--task", str(self.ao_home / "scheduled" / "kw-t1.md")],
                       check=True, capture_output=True)
        self.wait_runs(2)
        reports = sorted((self.ao_home / "runs").glob("*/report.md"))
        self.assertIn("exit code: 12", reports[-1].read_text())  # weekly budget reached


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(AIBOX and (AO_SRC / "bin" / "schedule.sh").exists() and shutil.which("patch"),
                     "set AIBOX_DIR to a weboko/ai-box checkout (and have `patch`)")
class MaxDurationPatchTest(KwTestCase):
    """integrations/ai-box/patches/0001: a hard wall-clock limit for orchestrated runs."""

    def setUp(self):
        super().setUp()
        self.ao = self.tmp / "agent-orchestrator"
        shutil.copytree(AO_SRC, self.ao)
        patch = ROOT / "integrations" / "ai-box" / "patches" / "0001-agent-orchestrator-max-duration.patch"
        subprocess.run(["patch", "-s", "-p4", "-d", str(self.ao), "-i", str(patch)], check=True)
        self.saved = {k: os.environ.get(k) for k in ("AO_HOME", "KW_AO_BIN", "PATH", "FAKE_AGENT_SLEEP", "FAKE_CRONTAB")}
        os.environ.update({"AO_HOME": str(self.tmp / "ao"), "KW_AO_BIN": str(self.ao / "bin"),
                           "PATH": f"{ROOT / 'tests' / 'fakes'}:{os.environ['PATH']}", "FAKE_AGENT_SLEEP": "30",
                           "FAKE_CRONTAB": str(self.tmp / "crontab.txt")})
        self.topic()

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        super().tearDown()

    def test_agent_is_stopped_and_next_run_recovers(self):
        self.kw("schedule", "run-now", "t1", "--max-duration", "2s")
        t0 = time.time()
        rj = None
        while time.time() - t0 < 20:
            f = next((self.tmp / "ao" / "runs").glob("*/run.json"), None)
            if f and json.loads(f.read_text())["status"] != "running":
                rj = json.loads(f.read_text())
                break
            time.sleep(0.3)
        self.assertIsNotNone(rj, "run was not stopped")
        self.assertLess(time.time() - t0, 15)
        self.assertEqual((rj["status"], rj["exit_code"], rj["max_duration"]), ("failed", "124", "2s"))
        # kinwing's run was left active by the killed agent; the next begin recovers it at once.
        active = runs.active_runs(self.kb, "t1")
        self.assertEqual(len(active), 1)
        r2, _ = runs.begin(self.kb, "t1")
        self.assertEqual(self.kb.load("run", active[0]["id"])[0]["status"], "interrupted")
        self.assertIn(active[0]["id"], r2["recovered_runs"])
