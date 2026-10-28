"""The private reader: a small local web app over the kb and the learning state.

stdlib only (http.server) and a static single-page app in ./static. Private by default:
binds 127.0.0.1, rejects requests whose Host header isn't an allowed host (DNS
rebinding), requires a custom header on every write (blocks cross-site form posts), and,
with KW_READER_TOKEN set, a token cookie. Responses carry a strict CSP. Source text and
agent-written prose are escaped (mdrender) before they reach the page.

This is not the published-report path: nothing here writes to ~/www, and create-report
never reads learning/.
"""

from __future__ import annotations

import hmac
import json
import mimetypes
import os
import re
import sys
import traceback
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import consolidate, export, ingest, mdrender, notify, store
from .kb import KB, parse_prompts, parse_sections
from .learning import Learning
from .store import KwError

STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = 1024 * 1024
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


class Api:
    """JSON views over the kb + learning state. Each method returns a dict."""

    def __init__(self, kb: KB):
        self.kb = kb
        self.L = Learning(kb)

    # ------------------------------------------------------------- helpers

    def _resolver(self):
        kb = self.kb

        def resolve(target: str):
            t = target.strip()
            if kb.exists("concept", t):
                return f"#/c/{t}", kb.load("concept", t)[0].get("title", t)
            slug = store.slugify(t)
            if kb.exists("concept", slug):
                return f"#/c/{slug}", kb.load("concept", slug)[0].get("title", t)
            for c in kb.metas("concept"):
                if c.get("title", "").lower() == t.lower() or t.lower() in [a.lower() for a in c.get("aliases") or []]:
                    return f"#/c/{c['id']}", c["title"]
            return None
        return resolve

    def md(self, text: str, para: bool = True) -> str:
        return mdrender.render(text or "", self._resolver(), para)

    def _evidence_view(self, eid: str, ev: dict, src: dict) -> dict | None:
        e = ev.get(eid)
        if not e:
            return None
        s = src.get(e.get("source"), {})
        para = None
        m = re.match(r"¶(\d+)", e.get("locator") or "")
        if m:
            para = int(m.group(1))
        return {"id": eid, "quote": e.get("quote"), "note": e.get("note"), "kind": e.get("kind"),
                "verified": e.get("quote_verified"), "locator": e.get("locator"), "para": para,
                "source": e.get("source"), "source_title": s.get("title"), "source_url": s.get("canonical_url"),
                "source_category": s.get("category")}

    def _claim_view(self, c: dict, ev: dict, src: dict) -> dict:
        return {"id": c["id"], "text": c["text"], "strength": c.get("strength"), "kind": c.get("kind"),
                "state": c.get("state"), "uncertainty": c.get("uncertainty"), "last_verified": c.get("last_verified"),
                "superseded_by": c.get("superseded_by"), "concepts": c.get("concepts") or [],
                "support": [x for x in (self._evidence_view(e, ev, src) for e in c.get("support") or []) if x],
                "counter": [x for x in (self._evidence_view(e, ev, src) for e in c.get("counter") or []) if x],
                "contradicts": c.get("contradicts") or []}

    def _concept_brief(self, c: dict, st: dict, ans_by: dict) -> dict:
        e = st["concepts"].get(c["id"]) or {}
        return {"id": c["id"], "title": c.get("title"), "summary": c.get("summary"),
                "perspective": c.get("perspective"), "prerequisites": c.get("prerequisites") or [],
                "related": c.get("related") or [], "updated": c.get("updated"),
                "inferred": self.L.infer(c["id"], st, ans_by.get(c["id"], [])),
                "self_report": (e.get("self_report") or {}).get("value"),
                "interest": (e.get("interest") or {}).get("value"),
                "progress": (e.get("observed") or {}).get("progress") or 0,
                "completed": bool((e.get("observed") or {}).get("completed_at"))}

    def _ans_by(self):
        out: dict[str, list] = {}
        for a in self.L.answers():
            out.setdefault(a["concept"], []).append(a)
        return out

    @staticmethod
    def _layers(concepts: list[dict]) -> list[list[str]]:
        """Group concepts into layers by prerequisite depth (foundations first)."""
        ids = {c["id"] for c in concepts}
        pre = {c["id"]: [p for p in c.get("prerequisites") or [] if p in ids] for c in concepts}
        depth: dict[str, int] = {}

        def d(x, seen=()):
            if x in depth:
                return depth[x]
            if x in seen:
                return 0  # a cycle: don't loop
            depth[x] = 0 if not pre[x] else 1 + max(d(p, seen + (x,)) for p in pre[x])
            return depth[x]

        for c in concepts:
            d(c["id"])
        layers: list[list[str]] = []
        for cid, k in sorted(depth.items(), key=lambda kv: kv[1]):
            while len(layers) <= k:
                layers.append([])
            layers[k].append(cid)
        return layers

    # ------------------------------------------------------------- views

    def home(self) -> dict:
        st = self.L.state()
        ans_by = self._ans_by()
        topics = []
        for t in self.kb.topics():
            cs = self.kb.metas("concept", t["id"])
            briefs = [self._concept_brief(c, st, ans_by) for c in cs]
            since, ch = self.L.changes_since_visit(t["id"])
            topics.append({
                "id": t["id"], "title": t["title"], "status": t.get("status"), "depth": t.get("depth"),
                "objective": t.get("objective"), "last_investigated": t.get("last_investigated"),
                "concepts": len(cs),
                "read": sum(1 for b in briefs if b["completed"] or b["inferred"]["status"] in
                            ("read", "practised", "shows understanding", "self-reported known")),
                "claims": sum(1 for c in self.kb.metas("claim", t["id"]) if c.get("state") == "current"),
                "open_questions": sum(1 for q in self.kb.metas("question", t["id"]) if q.get("status") == "open"),
                "changes_since_visit": len(ch), "last_visit": since,
                "scheduled": bool((t.get("schedule") or {}).get("enabled")),
            })
        lp = st.get("last_position")
        cont = None
        if lp and self.kb.exists(lp["kind"], lp["id"]):
            m = self.kb.load(lp["kind"], lp["id"])[0]
            o = (st["concepts" if lp["kind"] == "concept" else "sources"].get(lp["id"]) or {}).get("observed") or {}
            cont = {"kind": lp["kind"], "id": lp["id"], "title": m.get("title"), "progress": o.get("progress") or 0,
                    "para": o.get("para"), "at": lp.get("at")}
        return {"topics": topics, "continue": cont, "next": self.L.recommend(limit=4), "due": self.L.due(),
                "notifications": notify.items(self.kb.p)[-10:][::-1]}

    def topic(self, tid: str) -> dict:
        t = self.kb.topic(tid)
        st = self.L.state()
        ans_by = self._ans_by()
        ev = {e["id"]: e for e in self.kb.metas("evidence")}
        src = {s["id"]: s for s in self.kb.metas("source")}
        concepts = sorted(self.kb.metas("concept", tid), key=lambda c: c.get("title", ""))
        briefs = {c["id"]: self._concept_brief(c, st, ans_by) for c in concepts}
        claims = [c for c in self.kb.metas("claim", tid) if c.get("state") == "current"]
        order = {"strong": 0, "moderate": 1, "weak": 2, "contested": 3, "unsupported": 4}
        claims.sort(key=lambda c: order.get(c.get("strength"), 9))
        qs = self.kb.metas("question", tid)
        since, ch = self.L.changes_since_visit(tid)
        ov = self.kb.p.topic_dir(tid) / "overview.md"
        overview = ov.read_text(encoding="utf-8") if ov.exists() else ""
        overview = "\n".join(l for l in overview.splitlines() if not l.startswith("<!-- kinwing:"))
        overview = re.sub(r"^#\s+.*\n", "", overview.strip() + "\n", count=1)
        recs = self.L.recommend(topic=tid, limit=3)
        layers = self._layers(concepts)
        sources = []
        for s in sorted([s for s in src.values() if tid in (s.get("topics") or [])], key=lambda s: s.get("category", "")):
            o = (st["sources"].get(s["id"]) or {}).get("observed") or {}
            sources.append({"id": s["id"], "title": s.get("title"), "category": s.get("category"),
                            "url": s.get("canonical_url"), "access": s.get("access"), "why": s.get("why"),
                            "retrieved": s.get("retrieved"), "extraction": s.get("extraction"),
                            "progress": o.get("progress") or 0,
                            "evidence": sum(1 for e in ev.values() if e.get("source") == s["id"])})
        runs = sorted([r for r in self.kb.metas("run") if r.get("topic") == tid], key=lambda r: r.get("started") or "")
        return {
            "topic": {k: t.get(k) for k in ("id", "title", "description", "objective", "familiarity", "depth", "status",
                                             "last_investigated", "schedule", "perspectives", "frequency")},
            "overview_html": self.md(overview),
            "concepts": list(briefs.values()),
            "layers": layers,
            "start_here": [r["concept"] for r in recs],
            "recommendations": recs,
            "claims": [self._claim_view(c, ev, src) for c in claims],
            "unknowns": {
                "open_questions": [{"id": q["id"], "text": q["text"], "origin": q.get("origin"), "status": q["status"],
                                    "asked_by": q.get("asked_by"), "perspective": q.get("perspective")}
                                   for s_, w_, q in self.kb.ranked_questions(tid, ("open", "in_progress", "partial", "blocked"))],
                "contested": [c["id"] for c in claims if c.get("strength") == "contested"],
                "weak": [c["id"] for c in claims if c.get("strength") in ("weak", "unsupported") or c.get("kind") == "hypothesis"],
            },
            "answered": [{"id": q["id"], "text": q["text"], "result": q.get("result"), "asked_by": q.get("asked_by")}
                         for q in qs if q.get("status") == "answered"],
            "sources": sources,
            "changes": {"since": since, "items": ch[-40:][::-1]},
            "runs": [{"id": r["id"], "status": r.get("status"), "started": r.get("started"), "stats": r.get("stats"),
                      "stop_reason": r.get("stop_reason")} for r in runs[-5:][::-1]],
            "highlights": len(self.L.highlights(topic=tid)),
        }

    def concept(self, cid: str) -> dict:
        meta, body = self.kb.load("concept", cid)
        secs = parse_sections(body)
        st = self.L.state()
        ans_by = self._ans_by()
        ev = {e["id"]: e for e in self.kb.metas("evidence")}
        src = {s["id"]: s for s in self.kb.metas("source")}
        claims = [c for c in self.kb.metas("claim") if c.get("state") == "current"
                  and (cid in (c.get("concepts") or []) or c["id"] in (meta.get("claims") or []))]
        all_concepts = {c["id"]: c for c in self.kb.metas("concept")}

        def ref(x):
            c = all_concepts.get(x)
            return {"id": x, "title": c.get("title") if c else x, "exists": bool(c),
                    **({"inferred": self.L.infer(x, st, ans_by.get(x, []))["status"]} if c else {})}

        leads = [ref(c["id"]) for c in all_concepts.values() if cid in (c.get("prerequisites") or [])]
        related = [{**ref(r["id"]), "rel": r.get("rel")} for r in meta.get("related") or []]
        mine = {r["id"] for r in meta.get("related") or []}
        for c in all_concepts.values():
            back = [r for r in c.get("related") or [] if r.get("id") == cid]
            if back and c["id"] not in mine:
                related.append({**ref(c["id"]), "rel": back[0].get("rel", "related")})
        source_ids = list(meta.get("sources") or [])
        for c in claims:
            source_ids += [ev[e]["source"] for e in (c.get("support") or []) + (c.get("counter") or []) if e in ev]
        e = st["concepts"].get(cid) or {}
        return {
            "concept": {k: meta.get(k) for k in ("id", "title", "summary", "topics", "perspective", "aliases", "updated", "created")},
            "explanation_html": self.md(secs.get("Explanation", "")),
            "details_html": self.md(secs.get("Details", "")),
            "alternative_html": self.md(secs.get("Alternative explanation", "")),
            "has_previous_versions": bool(secs.get("Previous versions")),
            "prompts": parse_prompts(secs.get("Prompts", "")),
            "claims": [self._claim_view(c, ev, src) for c in claims],
            "prerequisites": [ref(p) for p in meta.get("prerequisites") or []],
            "leads_to": leads,
            "related": related,
            "sources": [{"id": s, "title": src[s].get("title"), "category": src[s].get("category"),
                         "url": src[s].get("canonical_url")} for s in store.uniq(source_ids) if s in src],
            "state": {"observed": e.get("observed") or {}, "self_report": e.get("self_report"),
                      "interest": e.get("interest"), "revisit": e.get("revisit"),
                      "inferred": self.L.infer(cid, st, ans_by.get(cid, []))},
            "highlights": self.L.highlights(target=f"concept:{cid}"),
            "answers": ans_by.get(cid, []),
            "questions": [{"id": q["id"], "text": q["text"], "status": q["status"], "result": q.get("result")}
                          for q in self.kb.metas("question") if cid in (q.get("concepts") or [])],
        }

    def source(self, sid: str, start: int = 1, limit: int = 1500) -> dict:
        meta, body = self.kb.load("source", sid)
        text = self.kb.source_text(sid) or ""
        paras = ingest.paragraphs(text)
        st = self.L.state()
        e = st["sources"].get(sid) or {}
        ev = [x for x in self.kb.metas("evidence") if x.get("source") == sid]
        evv = []
        for x in ev:
            m = re.match(r"¶(\d+)", x.get("locator") or "")
            claims = [c["id"] for c in self.kb.metas("claim") if x["id"] in (c.get("support") or []) + (c.get("counter") or [])]
            evv.append({"id": x["id"], "quote": x.get("quote"), "para": int(m.group(1)) if m else None,
                        "locator": x.get("locator"), "note": x.get("note"), "claims": claims})
        secs = parse_sections(body)
        return {
            "source": {k: meta.get(k) for k in ("id", "title", "authors", "organization", "canonical_url", "published",
                                                 "retrieved", "category", "rights", "access", "extraction",
                                                 "extraction_note", "topics", "assessment", "why", "content_type")},
            "summary_html": self.md(secs.get("Summary (AI-written)", ""), para=False),
            "paragraphs": paras[start - 1: start - 1 + limit],
            "start": start,
            "total_paragraphs": len(paras),
            "evidence": evv,
            "highlights": self.L.highlights(target=f"source:{sid}"),
            "state": {"observed": e.get("observed") or {}},
        }

    def search(self, q: str) -> dict:
        q = (q or "").strip().lower()
        if len(q) < 2:
            return {"results": []}
        res = []
        for c in self.kb.metas("concept"):
            if q in (c.get("title", "") + " " + c.get("summary", "") + " " + " ".join(c.get("aliases") or [])).lower():
                res.append({"kind": "concept", "id": c["id"], "title": c["title"], "snippet": c.get("summary")})
        for c in self.kb.metas("claim"):
            if c.get("state") == "current" and q in c["text"].lower():
                res.append({"kind": "claim", "id": c["id"], "title": c["text"], "topic": (c.get("topics") or [""])[0],
                            "concepts": c.get("concepts") or []})
        for s in self.kb.metas("source"):
            if q in (s.get("title") or "").lower():
                res.append({"kind": "source", "id": s["id"], "title": s["title"]})
        for h in self.L.highlights():
            if q in (h.get("quote", "") + " " + h.get("note", "")).lower():
                res.append({"kind": "highlight", "id": h["id"], "title": h["quote"][:120],
                            "target": f"{h['target_kind']}:{h['target_id']}"})
        return {"results": res[:60]}

    def questions(self) -> dict:
        rows = []
        for q in self.L.my_questions():
            rows.append({k: q.get(k) for k in ("id", "text", "status", "result", "topic", "concepts", "created",
                                                "last_evaluated", "context")})
        rows.sort(key=lambda q: q.get("created") or "", reverse=True)
        return {"questions": rows}


# ============================================================================ HTTP


def _allowed_hosts() -> set[str]:
    extra = {h.strip().lower() for h in os.environ.get("KW_READER_ALLOWED_HOSTS", "").split(",") if h.strip()}
    return {"localhost", "127.0.0.1", "[::1]", "::1"} | extra


class Handler(BaseHTTPRequestHandler):
    server_version = "kinwing-reader"
    api: Api = None  # set by serve()
    token: str = ""

    def log_message(self, fmt, *args):  # quieter, to stderr
        if os.environ.get("KW_READER_QUIET") != "1":
            sys.stderr.write("reader: " + (fmt % args) + "\n")

    # ------------------------------------------------------------- plumbing

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, code: int, msg: str):
        self._json({"error": msg}, code)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
        return name in _allowed_hosts()

    def _auth_ok(self) -> bool:
        if not self.token:
            return True
        cookie = self.headers.get("Cookie") or ""
        m = re.search(r"(?:^|;\s*)kw_token=([^;]+)", cookie)
        return bool(m and hmac.compare_digest(m.group(1), self.token))

    def _guard(self, write: bool) -> bool:
        if not self._host_ok():
            self._error(403, "host not allowed (set KW_READER_ALLOWED_HOSTS to add one)")
            return False
        if not self._auth_ok():
            self._error(401, "token required: open the reader once with ?token=<KW_READER_TOKEN>")
            return False
        if write:
            if self.headers.get("X-KW") != "1":
                self._error(403, "missing X-KW header")
                return False
            origin = self.headers.get("Origin")
            if origin:
                o = urllib.parse.urlsplit(origin)
                if (o.netloc or "").lower() != (self.headers.get("Host") or "").lower():
                    self._error(403, "cross-origin write refused")
                    return False
        return True

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise KwError("request too large", 2)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise KwError("invalid JSON", 2) from None
        if not isinstance(data, dict):
            raise KwError("expected a JSON object", 2)
        return data

    # ------------------------------------------------------------- dispatch

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        qs = urllib.parse.parse_qs(url.query)
        if self.token and "token" in qs and self._host_ok():
            if hmac.compare_digest(qs["token"][0], self.token):
                self._send(302, b"", "text/plain", {"Location": "/", "Set-Cookie":
                           f"kw_token={self.token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000"})
                return
        if not self._guard(write=False):
            return
        path = url.path
        try:
            if path == "/" or path == "/index.html":
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path.startswith("/api/"):
                return self._json(self._get_api(path[5:], qs))
            self._error(404, "not found")
        except KwError as e:
            self._error(404 if "no " in str(e)[:4] else 400, str(e))
        except Exception as e:  # pragma: no cover
            traceback.print_exc()
            self._error(500, f"internal error: {e}")

    def _write(self):
        if not self._guard(write=True):
            return
        path = urllib.parse.urlsplit(self.path).path
        try:
            if not path.startswith("/api/"):
                return self._error(404, "not found")
            self._json(self._post_api(self.command, path[5:], self._body()))
        except KwError as e:
            self._error(400, str(e))
        except Exception as e:  # pragma: no cover
            traceback.print_exc()
            self._error(500, f"internal error: {e}")

    do_POST = _write
    do_PATCH = _write
    do_DELETE = _write

    def _static(self, rel: str):
        f = (STATIC / rel).resolve()
        if STATIC not in f.parents or not f.is_file():
            return self._error(404, "not found")
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)

    def _get_api(self, path: str, qs: dict):
        a = self.api
        parts = [urllib.parse.unquote(p) for p in path.split("/") if p]
        one = lambda k, d=None: (qs.get(k) or [d])[0]  # noqa: E731
        if parts == ["home"]:
            return a.home()
        if len(parts) == 2 and parts[0] == "topic":
            return a.topic(parts[1])
        if len(parts) == 2 and parts[0] == "concept":
            return a.concept(parts[1])
        if len(parts) == 2 and parts[0] == "source":
            return a.source(parts[1], int(one("start", 1)))
        if parts == ["highlights"]:
            return {"highlights": a.L.highlights(topic=one("topic"))}
        if parts == ["questions"]:
            return a.questions()
        if parts == ["next"]:
            return {"next": a.L.recommend(topic=one("topic"), limit=int(one("limit", 6)))}
        if parts == ["search"]:
            return a.search(one("q", ""))
        if parts == ["notifications"]:
            return {"notifications": notify.items(a.kb.p)[::-1]}
        if parts == ["sessions"]:
            return {"sessions": a.L.sessions()[:10]}
        if len(parts) == 2 and parts[0] == "sessions":
            return a.L.session(parts[1])
        if len(parts) == 2 and parts[0] == "consolidation":
            res = consolidate.analyze(a.kb, parts[1])
            return {k: len(v) for k, v in res.items()}
        raise KwError("no such endpoint")

    def _post_api(self, method: str, path: str, d: dict):
        a, L = self.api, self.api.L
        parts = [urllib.parse.unquote(p) for p in path.split("/") if p]
        if method == "POST" and parts == ["progress"]:
            return L.record_progress(d.get("kind"), d.get("id"), d.get("fraction"), d.get("para"), d.get("depth"),
                                     float(d.get("seconds") or 0), bool(d.get("completed")), bool(d.get("view")))
        if method == "POST" and parts == ["mark"]:
            return L.self_report(d.get("concept"), d.get("value"), d.get("note"))
        if method == "POST" and parts == ["interest"]:
            return L.set_interest(d.get("concept"), d.get("value"))
        if method == "POST" and parts == ["revisited"]:
            return L.mark_revisited(d.get("concept"))
        if method == "POST" and len(parts) == 3 and parts[0] == "topic" and parts[2] == "seen":
            return L.visit_topic(parts[1])
        if method == "POST" and parts == ["highlights"]:
            return L.add_highlight(d.get("kind"), d.get("id"), d.get("quote"), note=d.get("note") or "",
                                   tags=d.get("tags"), prefix=d.get("prefix") or "", suffix=d.get("suffix") or "",
                                   section=d.get("section") or "")
        if len(parts) == 2 and parts[0] == "highlights":
            if method == "PATCH":
                return L.update_highlight(parts[1], note=d.get("note"), tags=d.get("tags"))
            if method == "DELETE":
                L.delete_highlight(parts[1])
                return {"deleted": parts[1]}
        if method == "POST" and parts == ["ask"]:
            q = L.ask(d.get("kind") or "question", d.get("text") or "", topic=d.get("topic"),
                      concept=d.get("concept"), target=d.get("target"), quote=d.get("quote"))
            return {"question": {k: q.get(k) for k in ("id", "text", "status", "topic")},
                    "duplicate": bool(q.get("_duplicate"))}
        if method == "POST" and parts == ["answers"]:
            return L.add_answer(d.get("concept"), d.get("prompt") or "", d.get("text") or "", d.get("kind") or "explain")
        if method == "POST" and parts == ["sessions"]:
            return L.create_session(int(d.get("minutes") or 15), d.get("topic") or None)
        if method == "POST" and len(parts) == 3 and parts[0] == "sessions" and parts[2] == "step":
            return L.session_step(parts[1], int(d.get("index")), bool(d.get("done", True)))
        if method == "POST" and parts == ["export"]:
            return export.obsidian(a.kb, highlights=d.get("highlights") or [], concepts=d.get("concepts") or [])
        if method == "POST" and parts == ["notifications", "ack"]:
            return {"acked": notify.ack(a.kb.p, d.get("ids") or None)}
        raise KwError("no such endpoint")


def make_server(kb: KB, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    store.ensure_layout(kb.p)
    handler = type("KwHandler", (Handler,), {"api": Api(kb), "token": os.environ.get("KW_READER_TOKEN", "")})
    srv = ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True
    return srv


def serve(kb: KB, host: str = "127.0.0.1", port: int = 8765) -> None:
    srv = make_server(kb, host, port)
    loopback = host in ("127.0.0.1", "localhost", "::1")
    print(f"kinwing reader on http://{'localhost' if loopback else host}:{srv.server_address[1]}/  (knowledge home {kb.p.home})",
          file=sys.stderr)
    if not loopback and not os.environ.get("KW_READER_TOKEN"):
        print("reader: listening beyond loopback without KW_READER_TOKEN. That is fine inside a container whose "
              "port is published on 127.0.0.1 only; otherwise set a token.", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        srv.server_close()
