"""Paths, locking, atomic writes, identifiers and entity files.

Layout of a knowledge home ($KW_HOME):

    kb/         git repository: topics, questions, sources (metadata), evidence, claims,
                concepts, runs. The derived knowledge. Agent-orchestrator's workdir.
    library/    raw material: original files and extracted text per source. Not in git
                (can be large or copyrighted); rebuildable by re-fetching public sources.
    learning/   the user's personal learning state: progress, highlights, answers.
                Never read by report generation; never published.
    runtime/    locks, notifications, run briefs. Disposable except notifications.
    exports/    default target for Obsidian exports (KW_EXPORT_DIR overrides).
"""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
from pathlib import Path

from . import yamlio

ID_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


class KwError(Exception):
    """An error meant for the user (printed without a traceback)."""

    def __init__(self, msg: str, code: int = 1):
        super().__init__(msg)
        self.code = code


# --------------------------------------------------------------------------- time


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_ms() -> str:
    """Millisecond timestamps for ordering events (change log, visits) within a second."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def today() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def parse_ts(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    s = str(s).strip()
    try:
        if len(s) == 10:
            return dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError:
        return None


# --------------------------------------------------------------------------- paths


class Paths:
    def __init__(self, home: str | os.PathLike | None = None):
        raw = home or os.environ.get("KW_HOME") or "~/knowledge"
        self.home = Path(os.path.expanduser(str(raw))).resolve()
        self.kb = self.home / "kb"
        self.library = self.home / "library"
        self.learning = self.home / "learning"
        self.runtime = self.home / "runtime"
        exp = os.environ.get("KW_EXPORT_DIR")
        self.exports = Path(os.path.expanduser(exp)).resolve() if exp else self.home / "exports" / "obsidian"
        self.www = Path(os.path.expanduser(os.environ.get("WWW_ROOT", "~/www"))).resolve()

    # kb
    def topic_dir(self, tid: str) -> Path:
        return self.kb / "topics" / tid

    def entity_dir(self, kind: str) -> Path:
        return self.kb / KIND_DIRS[kind]

    def entity_path(self, kind: str, eid: str) -> Path:
        return self.entity_dir(kind) / f"{eid}.md"

    def lock_file(self) -> Path:
        return self.runtime / "kb.lock"

    def check_private_location(self) -> None:
        """Refuse a knowledge home or export dir inside the public web root."""
        for label, p in (("KW_HOME", self.home), ("KW_EXPORT_DIR", self.exports)):
            if p == self.www or self.www in p.parents:
                raise KwError(
                    f"{label}={p} is inside the public web root {self.www} (WWW_ROOT). "
                    "The knowledge base and personal exports are private; move them outside it."
                )


KIND_DIRS = {
    "question": "questions",
    "source": "sources",
    "evidence": "evidence",
    "claim": "claims",
    "concept": "concepts",
    "run": "runs",
}
ID_PREFIX = {"question": "q", "evidence": "ev", "claim": "cl", "run": "run"}


def ensure_layout(p: Paths, git: bool = True) -> None:
    p.check_private_location()
    for d in [p.kb / "topics", p.library, p.learning / "highlights", p.learning / "answers",
              p.learning / "sessions", p.runtime, p.exports]:
        d.mkdir(parents=True, exist_ok=True)
    for kind in KIND_DIRS:
        p.entity_dir(kind).mkdir(parents=True, exist_ok=True)
    gi = p.kb / ".gitignore"
    if not gi.exists():
        atomic_write(gi, "# kinwing: raw material lives in ../library, outside git\n*.tmp\n.kw-*\n")
    if git and not (p.kb / ".git").exists() and _has_git():
        subprocess.run(["git", "init", "-q", "-b", "main", str(p.kb)], check=False)


def _has_git() -> bool:
    from shutil import which

    return which("git") is not None


# --------------------------------------------------------------------------- locking

_tl = threading.local()
_proc_lock = threading.RLock()


@contextlib.contextmanager
def locked(p: Paths):
    """Exclusive lock on the knowledge home for a read-modify-write sequence.

    flock(2) on a file in runtime/: works across processes and across containers that
    bind-mount the same directory on one host. Re-entrant within a thread.
    """
    depth = getattr(_tl, "depth", 0)
    if depth:
        _tl.depth = depth + 1
        try:
            yield
        finally:
            _tl.depth -= 1
        return
    p.runtime.mkdir(parents=True, exist_ok=True)
    with _proc_lock:
        fd = os.open(p.lock_file(), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            _tl.depth = 1
            try:
                yield
            finally:
                _tl.depth = 0
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


# --------------------------------------------------------------------------- files


def atomic_write(path: Path, text: str) -> None:
    """Write via a temp file in the same directory, fsync, then rename over the target.

    A crash leaves either the old or the new file, never a half-written one.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def append_line(path: Path, obj: dict) -> None:
    """Append one JSON line (O_APPEND writes of a single line don't interleave)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a torn last line after a crash: skip it
    return out


def read_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, obj) -> None:
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def read_yaml(path: Path) -> dict:
    return yamlio.load(Path(path).read_text(encoding="utf-8")) or {}


def write_yaml(path: Path, obj: dict, header: str = "") -> None:
    atomic_write(path, (header + "\n" if header else "") + yamlio.dump(obj))


# --------------------------------------------------------------------------- entities


def read_entity(path: Path) -> tuple[dict, str]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        return yamlio.split_frontmatter(text)
    except yamlio.YamlError as e:
        raise KwError(f"{path}: invalid frontmatter: {e}") from e


def write_entity(path: Path, meta: dict, body: str = "") -> None:
    atomic_write(path, yamlio.join_frontmatter(meta, body))


def slugify(text: str, maxlen: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    if len(s) > maxlen:
        s = s[: maxlen + 1].rsplit("-", 1)[0] or s[:maxlen]
    return s


def valid_slug(s: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", s or ""))


def new_id(p: Paths, kind: str) -> str:
    prefix = ID_PREFIX[kind]
    date = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    for _ in range(100):
        rand = "".join(secrets.choice(ID_ALPHABET) for _ in range(4))
        eid = f"{prefix}-{date}-{rand}"
        if not p.entity_path(kind, eid).exists():
            return eid
    raise KwError("could not allocate an id")  # pragma: no cover


def kind_of(eid: str) -> str | None:
    m = re.match(r"^(q|ev|cl|run|src)-", eid or "")
    if not m:
        return None
    return {"q": "question", "ev": "evidence", "cl": "claim", "run": "run", "src": "source"}[m.group(1)]


def split_list(v) -> list[str]:
    """CLI helper: 'a,b, c' or a list -> ['a', 'b', 'c']."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        out = []
        for x in v:
            out.extend(split_list(x))
        return out
    return [x.strip() for x in str(v).split(",") if x.strip()]


def uniq(seq) -> list:
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
