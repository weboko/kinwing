"""kinwing inside ai-box, with Docker: skills linking, shared knowledge, scheduling,
persistence across container recreation, and concurrent writers in two containers.

Uses a copy of a real weboko/ai-box checkout (AIBOX_DIR): its docker-compose.yml,
entrypoint.sh and box-supervisor.sh, plus kinwing's generated override. Only the image of
the `box` service is replaced by a small stand-in without the Claude/Codex binaries
(they need logins), so what runs is ai-box's own startup logic. Slow (builds images):
runs only with KW_TEST_DOCKER=1.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tests.util import ROOT

AIBOX = os.environ.get("AIBOX_DIR", "")
PORT = int(os.environ.get("KW_TEST_READER_PORT", "18765"))
SIM_DOCKERFILE = """FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 jq git cron caddy procps ca-certificates \\
    && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /usr/local/bin/box-entrypoint.sh
COPY box-supervisor.sh /usr/local/bin/box-supervisor.sh
RUN chmod 0755 /usr/local/bin/box-entrypoint.sh /usr/local/bin/box-supervisor.sh
ENV HOME=/ai-box BOX_AGENTS=""
WORKDIR /ai-box
ENTRYPOINT ["/usr/local/bin/box-entrypoint.sh"]
CMD ["box-supervisor.sh"]
"""
SIM = """services:
  box:
    build:
      context: .
      dockerfile: Dockerfile.sim
    image: kinwing-test-aibox-sim:latest
"""


def have_docker():
    return shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@unittest.skipUnless(os.environ.get("KW_TEST_DOCKER") == "1" and AIBOX and have_docker(),
                     "set KW_TEST_DOCKER=1 and AIBOX_DIR, with a working Docker daemon")
class AiBoxIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="kw-aibox-"))
        cls.aibox = cls.tmp / "ai-box"
        shutil.copytree(AIBOX, cls.aibox, ignore=shutil.ignore_patterns(".git"))
        subprocess.run(["git", "init", "-q"], cwd=cls.aibox, check=True)
        subprocess.run(["git", "add", "-A"], cwd=cls.aibox, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "base"], cwd=cls.aibox, check=True)
        cls.knowledge = cls.tmp / "knowledge"
        out = subprocess.run([str(ROOT / "integrations" / "ai-box" / "install.sh"), str(cls.aibox),
                              "--knowledge", str(cls.knowledge), "--port", str(PORT), "--apply-patches"],
                             capture_output=True, text=True, check=True).stdout
        cls.install_out = out
        (cls.aibox / "docker-compose.sim.yml").write_text(SIM)
        (cls.aibox / "Dockerfile.sim").write_text(SIM_DOCKERFILE)
        cls.compose = ["docker", "compose", "-p", "kwtest", "-f", "docker-compose.yml", "-f", "docker-compose.override.yml",
                       "-f", "docker-compose.sim.yml", "--profile", "box"]
        # Build first with plain `docker build` (host network: works behind a local proxy too).
        for tag, ctx, extra in (("kinwing:latest", ROOT, []),
                                ("kinwing-test-aibox-sim:latest", cls.aibox, ["-f", str(cls.aibox / "Dockerfile.sim")])):
            subprocess.run(["docker", "build", "-q", "--network", "host", "-t", tag, *extra, str(ctx)], check=True,
                           capture_output=True)
        cls.dc("up", "-d", "box", "kinwing-reader")
        cls.wait_reader()

    @classmethod
    def tearDownClass(cls):
        cls.dc("down", "-v", check=False)
        subprocess.run(["docker", "run", "--rm", "-v", f"{cls.tmp}:/t", "ubuntu:24.04", "rm", "-rf", "/t/knowledge", "/t/ai-box/ai-box"],
                       capture_output=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def dc(cls, *args, check=True):
        r = subprocess.run(cls.compose + list(args), cwd=cls.aibox, capture_output=True, text=True)
        if check and r.returncode != 0:
            raise AssertionError(f"docker compose {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
        return r

    @classmethod
    def box(cls, cmd: str, check=True) -> str:
        r = cls.dc("exec", "-T", "box", "bash", "-lc", cmd, check=False)
        if check and r.returncode != 0:
            raise AssertionError(f"in box: {cmd}\n{r.stdout}\n{r.stderr}")
        return r.stdout

    @classmethod
    def wait_reader(cls, timeout=60):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/home", timeout=2) as r:
                    return json.loads(r.read())
            except Exception:  # noqa: BLE001
                time.sleep(1)
        raise AssertionError("reader did not come up")

    def api(self, method, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-KW": "1", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    KW = "/opt/box-context/skills/knowledge-research/bin/kw"

    def test_1_skills_are_linked_for_both_agents(self):
        out = self.box("ls -l $CLAUDE_CONFIG_DIR/skills/ $CODEX_HOME/skills/")
        self.assertEqual(out.count("knowledge-research -> /opt/box-context/skills/knowledge-research"), 2)
        self.assertEqual(out.count("knowledge-learn -> /opt/box-context/skills/knowledge-learn"), 2)
        self.assertIn("name: knowledge-research", self.box("cat $CLAUDE_CONFIG_DIR/skills/knowledge-research/SKILL.md"))
        self.assertIn("/knowledge", self.box("echo $KW_HOME"))

    def test_2_shared_knowledge_and_schedule(self):
        self.box(f"{self.KW} topic new --title 'Docker test topic' --id dt --objective 'check the wiring'")
        self.box(f"{self.KW} q add 'Does the reader see this?' --topic dt")
        home = self.api("GET", "home")
        self.assertEqual([t["id"] for t in home["topics"]], ["dt"])  # the reader container sees the box's writes
        out = self.box(f"{self.KW} schedule add dt --cron '0 9 * * 1' --max-duration 30m")
        self.assertIn("Scheduled kw-dt", out)
        self.assertIn("kw-dt.md", self.box("crontab -l"))
        self.assertIn("max_duration", self.box("cat ~/.agent-orchestrator/scheduled/kw-dt.md"))

    def test_3_concurrent_writers_in_two_containers(self):
        def from_box(i):
            return self.box(f"{self.KW} q add 'Box question {i}?' --topic dt", check=False)

        def from_reader(i):
            return self.api("POST", "ask", {"kind": "question", "text": f"Reader question {i}?", "topic": "dt"})

        with ThreadPoolExecutor(8) as ex:
            list(ex.map(from_box, range(12)))
            list(ex.map(from_reader, range(12)))
        qs = json.loads(self.box(f"{self.KW} q list --topic dt --json"))
        texts = {q["text"] for q in qs}
        self.assertTrue(all(f"Box question {i}?" in texts for i in range(12)))
        self.assertTrue(all(f"Reader question {i}?" in texts for i in range(12)))
        self.assertIn("0 error(s)", self.box(f"{self.KW} check"))
        # every change-log line survived intact
        lines = Path(self.knowledge, "kb", "topics", "dt", "changes.jsonl").read_text().splitlines()
        self.assertTrue(all(json.loads(l) for l in lines))

    def test_4_state_survives_recreation(self):
        self.api("POST", "progress", {"kind": "concept", "id": self.concept(), "fraction": 0.6, "para": 2, "view": True})
        self.dc("up", "-d", "--force-recreate", "box", "kinwing-reader")
        self.wait_reader()
        time.sleep(3)  # box-supervisor syncs the crontab before starting cron
        t = self.api("GET", "topic/dt")
        self.assertEqual(t["topic"]["id"], "dt")
        c = self.api("GET", f"concept/{self.concept()}")
        self.assertEqual(c["state"]["observed"]["para"], 2)          # reading progress kept
        self.assertIn("kw-dt.md", self.box("crontab -l"))            # schedule rebuilt by ai-box on start
        self.assertIn("dt", self.box(f"{self.KW} status"))

    def concept(self):
        if not getattr(type(self), "_concept", None):
            self.box(f"{self.KW} concept add --topic dt --title 'Wiring' --id wiring --summary 'How the parts connect.'", check=False)
            type(self)._concept = "wiring"
        return "wiring"


if __name__ == "__main__":
    unittest.main()
