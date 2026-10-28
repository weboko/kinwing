"""A durable notification queue: runtime/notifications.jsonl.

Research runs add an entry only for things worth the user's attention (an important
finding, a blocker, a recommended action). Nothing is pushed anywhere; the reader's inbox,
`kw notify list` and the knowledge-learn skill surface them, and acking hides them.
"""

from __future__ import annotations

import json
import secrets

from . import store
from .store import Paths, now

SEVERITIES = ("info", "important", "action", "blocker")


def _file(p: Paths):
    return p.runtime / "notifications.jsonl"


def add(p: Paths, message: str, topic: str = "", severity: str = "info", run: str = "") -> dict:
    if severity not in SEVERITIES:
        raise store.KwError(f"severity must be one of {', '.join(SEVERITIES)}", 2)
    entry = {"id": "n-" + now().replace("-", "").replace(":", "")[:13] + "-" + secrets.token_hex(2),
             "at": now(), "topic": topic, "severity": severity, "message": message, "run": run, "acked": False}
    store.append_line(_file(p), entry)
    return entry


def items(p: Paths, include_acked: bool = False) -> list[dict]:
    out = store.read_jsonl(_file(p))
    return out if include_acked else [n for n in out if not n.get("acked")]


def ack(p: Paths, ids: list[str] | None = None) -> int:
    with store.locked(p):
        rows = store.read_jsonl(_file(p))
        n = 0
        for r in rows:
            if not r.get("acked") and (not ids or r["id"] in ids):
                r["acked"] = True
                r["acked_at"] = now()
                n += 1
        store.atomic_write(_file(p), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return n
