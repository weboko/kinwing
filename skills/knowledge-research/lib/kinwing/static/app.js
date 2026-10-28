/* kinwing reader — a small dependency-free single-page app.
 * Data comes from /api/*; every write sends X-KW: 1. Text from the knowledge base is
 * inserted with textContent; only server-rendered *_html fields (escaped by mdrender)
 * use innerHTML. */
"use strict";

const view = document.getElementById("view");
const LS = { get(k, d) { try { return JSON.parse(localStorage.getItem("kw:" + k)) ?? d; } catch { return d; } },
             set(k, v) { try { localStorage.setItem("kw:" + k, JSON.stringify(v)); } catch {} } };

// ------------------------------------------------------------------ DOM helpers
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k === "html") el.innerHTML = v; // only server-sanitized HTML
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const setView = (...nodes) => view.replaceChildren(...nodes.flat(Infinity).filter((n) => n !== null && n !== undefined && n !== false));
const chip = (text, cls) => h("span", { class: "chip " + (cls || "") }, text);
const link = (href, text, cls) => h("a", { href, class: cls }, text);
const ext = (href, text) => h("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);
const fmtDate = (s) => (s ? String(s).slice(0, 16).replace("T", " ") : "never");
const pct = (x) => Math.round(100 * (x || 0)) + "%";
function bar(fraction) { const b = h("div", { class: "progress" }, h("i")); b.firstChild.style.width = pct(fraction); return b; }
function toast(msg, ms = 3200) {
  const t = document.getElementById("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms);
}
const statusClass = (s) => ({ "read": "read", "shows understanding": "understanding", "self-reported known": "known",
  "started": "started", "practised": "practised", "needs another look": "confused" }[s] || "");

// ------------------------------------------------------------------ API
async function call(method, path, body) {
  const opt = { method, headers: {} };
  if (method !== "GET") { opt.headers["X-KW"] = "1"; opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body || {}); }
  const r = await fetch("/api/" + path, opt);
  const data = await r.json().catch(() => ({ error: r.statusText }));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}
const api = { get: (p) => call("GET", p), post: (p, b) => call("POST", p, b), patch: (p, b) => call("PATCH", p, b), del: (p) => call("DELETE", p) };

// ------------------------------------------------------------------ reading tracker
// Records observed behaviour only: how far the user scrolled, where they were, time spent.
let tracker = null;
class Tracker {
  constructor(kind, id, container, depth) {
    Object.assign(this, { kind, id, container, depth, last: 0, sent: -1, para: null, t0: Date.now(), done: false });
    this.onScroll = () => this.measure();
    window.addEventListener("scroll", this.onScroll, { passive: true });
    this.timer = setInterval(() => this.flush(), 5000);
    this.onHide = () => { if (document.visibilityState === "hidden") this.flush(); };
    document.addEventListener("visibilitychange", this.onHide);
    api.post("progress", { kind, id, view: true, depth }).catch(() => {});
    setTimeout(() => this.measure(), 300);
  }
  measure() {
    const r = this.container.getBoundingClientRect();
    const total = Math.max(1, r.height);
    const seen = Math.min(total, Math.max(0, window.innerHeight - r.top));
    this.last = Math.max(this.last, seen / total);
    const paras = this.container.querySelectorAll("[data-para]");
    for (const p of paras) { if (p.getBoundingClientRect().bottom > 90) { this.para = Number(p.dataset.para); break; } }
  }
  flush(final) {
    const secs = (Date.now() - this.t0) / 1000;
    if (document.visibilityState === "hidden" && !final) { this.t0 = Date.now(); }
    const fraction = Math.round(this.last * 100) / 100;
    const completed = !this.done && fraction >= 0.97 && secs + (this.acc || 0) > 15 && this.depth !== "glance";
    if (fraction === this.sent && !completed && secs < 4) return;
    this.acc = (this.acc || 0) + secs; this.t0 = Date.now(); this.sent = fraction;
    if (completed) this.done = true;
    const body = { kind: this.kind, id: this.id, fraction, para: this.para, depth: this.depth, seconds: secs, completed };
    fetch("/api/progress", { method: "POST", keepalive: true, headers: { "X-KW": "1", "Content-Type": "application/json" },
      body: JSON.stringify(body) }).catch(() => {});
  }
  stop() { this.flush(true); clearInterval(this.timer); window.removeEventListener("scroll", this.onScroll);
    document.removeEventListener("visibilitychange", this.onHide); }
}

// ------------------------------------------------------------------ highlights
// Text-quote anchoring: find the quote in the container's text (whitespace-insensitive) and wrap it.
function textIndex(root) {
  const nodes = []; let text = "";
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement && n.parentElement.closest(".pn, .no-hl") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT) });
  // Collapse whitespace while keeping a map back to (node, offset).
  const map = []; let prevSpace = true;
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const s = n.nodeValue;
    for (let i = 0; i < s.length; i++) {
      const ch = /\s/.test(s[i]) ? " " : s[i];
      if (ch === " " && prevSpace) continue;
      prevSpace = ch === " "; text += ch; map.push([n, i]);
    }
    nodes.push(n);
  }
  return { text, map };
}
const norm = (s) => s.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/\s+/g, " ").trim();
function applyHighlights(scope, highlights, onClick) {
  for (const hl of highlights) {
    const idx = textIndex(scope);
    const q = norm(hl.quote);
    let pos = idx.text.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').indexOf(q);
    if (pos < 0 || !q) continue;
    if (hl.prefix) { // disambiguate repeated passages
      const alt = idx.text.indexOf(norm(hl.prefix).slice(-20) + " " + q);
      if (alt >= 0) pos = alt + norm(hl.prefix).slice(-20).length + 1;
    }
    const make = () => { const m = h("mark", { class: "hl" + (hl.note ? " has-note" : ""), title: hl.note || "Your highlight", dataset: { id: hl.id } });
      m.addEventListener("click", (e) => { e.stopPropagation(); onClick(hl); }); return m; };
    try { wrapSegments(idx.map, pos, pos + q.length, make); } catch (e) { /* overlapping highlight: skip */ }
  }
}
function wrapSegments(map, start, end, make) {
  const segs = []; let i = start;
  while (i < end) { const node = map[i][0]; let j = i; while (j + 1 < end && map[j + 1][0] === node) j++;
    segs.push([node, map[i][1], map[j][1] + 1]); i = j + 1; }
  for (const [node, a, b] of segs.reverse()) { // right to left keeps earlier offsets valid
    const r = document.createRange(); r.setStart(node, a); r.setEnd(node, b); r.surroundContents(make());
  }
}

// Selection toolbar: highlight / note / ask / not convinced on any [data-hl-scope] text.
const seltool = document.getElementById("seltool");
let selCtx = null;
function currentSelection() {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  const range = sel.getRangeAt(0);
  const el = range.commonAncestorContainer.nodeType === 1 ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement;
  const scope = el && el.closest("[data-hl-scope]");
  const quote = norm(sel.toString());
  if (!scope || quote.length < 3) return null;
  const pre = document.createRange(); pre.setStart(scope, 0); pre.setEnd(range.startContainer, range.startOffset);
  const before = norm(pre.toString());
  const sec = el.closest("[data-section]");
  return { scope, quote, prefix: before.slice(-60), kind: scope.dataset.kind, id: scope.dataset.id,
           section: sec ? sec.dataset.section : "", rect: range.getBoundingClientRect() };
}
function showSeltool() {
  selCtx = currentSelection();
  if (!selCtx) { seltool.hidden = true; return; }
  seltool.hidden = false;
  const r = selCtx.rect;
  seltool.style.top = (window.scrollY + r.top - seltool.offsetHeight - 8) + "px";
  seltool.style.left = Math.max(8, Math.min(window.scrollX + r.left, window.scrollX + innerWidth - seltool.offsetWidth - 8)) + "px";
}
document.addEventListener("mouseup", () => setTimeout(showSeltool, 0));
document.addEventListener("keyup", (e) => { if (e.key === "Shift" || e.key.startsWith("Arrow")) showSeltool(); });
document.addEventListener("selectionchange", () => { clearTimeout(showSeltool._t); showSeltool._t = setTimeout(showSeltool, 350); });
seltool.addEventListener("mousedown", (e) => e.preventDefault());
seltool.addEventListener("click", async (e) => {
  const act = e.target.dataset.act; if (!act || !selCtx) return;
  const ctx = selCtx; seltool.hidden = true; window.getSelection().removeAllRanges();
  if (act === "hl") return saveHighlight(ctx, "");
  if (act === "note") return modal("Your note on this passage", ctx.quote, "What do you think? (saved as your own words)", (t) => saveHighlight(ctx, t));
  const kind = act === "challenge" ? "challenge" : "question";
  const title = kind === "challenge" ? "What doesn't convince you?" : "What do you want to know?";
  return modal(title, ctx.quote, kind === "challenge" ? "Optional: why you doubt it" : "Your question", (t) => ask(kind, t, ctx));
});
async function saveHighlight(ctx, note) {
  try {
    await api.post("highlights", { kind: ctx.kind, id: ctx.id, quote: ctx.quote, prefix: ctx.prefix, note, section: ctx.section });
    toast(note ? "Highlight and note saved" : "Highlighted"); rerender();
  } catch (err) { toast("Couldn't save: " + err.message); }
}
async function ask(kind, text, ctx) {
  const body = { kind, text, quote: ctx && ctx.quote, target: ctx && ctx.kind ? ctx.kind + ":" + ctx.id : null,
    concept: (ctx && ctx.concept) || (ctx && ctx.kind === "concept" ? ctx.id : null),
    topic: (ctx && ctx.topic) || (ctx && ctx.kind === "overview" ? ctx.id : null) || currentTopic };
  try {
    const r = await api.post("ask", body);
    toast((r.duplicate ? "Already in the research queue: " : "Added to the research queue: ") + r.question.id, 4500);
    rerender();
  } catch (err) { toast("Couldn't add: " + err.message); }
}
function modal(title, quote, placeholder, onSave, initial = "", allowEmpty = true) {
  const ta = h("textarea", { placeholder }); ta.value = initial;
  const close = () => bg.remove();
  const bg = h("div", { class: "modal-bg", onclick: (e) => { if (e.target === bg) close(); } },
    h("div", { class: "modal", role: "dialog", "aria-label": title },
      h("h3", { text: title }), quote ? h("div", { class: "quote", text: quote }) : null, ta,
      h("div", { class: "actions" }, h("span", { class: "spacer" }),
        h("button", { onclick: close }, "Cancel"),
        h("button", { class: "primary", onclick: () => { if (!allowEmpty && !ta.value.trim()) return ta.focus(); close(); onSave(ta.value.trim()); } }, "Save"))));
  document.body.append(bg); ta.focus();
  ta.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) bg.querySelector(".primary").click(); });
}
function highlightMenu(hl) {
  modal("Your highlight", hl.quote, "Your note (empty to keep none)", async (t) => {
    await api.patch("highlights/" + hl.id, { note: t }); toast("Note saved"); rerender();
  }, hl.note || "");
  const box = document.querySelector(".modal .actions");
  box.prepend(h("button", { onclick: async () => { if (!confirm("Remove this highlight?")) return;
    await api.del("highlights/" + hl.id); document.querySelector(".modal-bg").remove(); toast("Removed"); rerender(); } }, "Remove"));
}

// ------------------------------------------------------------------ router
let currentTopic = null;
let rerender = () => route();
async function route() {
  if (tracker) { tracker.stop(); tracker = null; }
  seltool.hidden = true;
  const hash = location.hash.replace(/^#\/?/, "");
  const [path, query] = hash.split("?");
  const params = new URLSearchParams(query || "");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === (parts[0] || "home")));
  try {
    if (!parts.length) await homeView();
    else if (parts[0] === "t") await topicView(parts[1], params.get("tab") || LS.get("tab:" + parts[1], "overview"));
    else if (parts[0] === "c") await conceptView(parts[1]);
    else if (parts[0] === "s") await sourceView(parts[1], Number(params.get("p")) || null);
    else if (parts[0] === "highlights") await highlightsView();
    else if (parts[0] === "questions") await questionsView();
    else if (parts[0] === "session") await sessionView(parts[1]);
    else if (parts[0] === "search") await searchView(params.get("q") || "");
    else setView(h("p", { text: "Not found." }));
  } catch (err) {
    setView(h("div", { class: "panel notice" }, h("h2", { text: "Couldn't load this page" }), h("p", { text: err.message }),
      link("#/", "← Home")));
  }
  renderSessionBar();
}
window.addEventListener("hashchange", () => { window.scrollTo(0, 0); route(); });
document.getElementById("search").addEventListener("submit", (e) => {
  e.preventDefault(); const q = new FormData(e.target).get("q"); location.hash = "#/search?q=" + encodeURIComponent(q);
});

// ------------------------------------------------------------------ home
async function homeView() {
  currentTopic = null;
  const d = await api.get("home");
  const out = [h("h1", { text: "Your knowledge" })];
  if (d.notifications.length) {
    out.push(h("section", { class: "panel notice" }, h("h2", { text: "From your research agents" }),
      h("ul", { class: "plain" }, d.notifications.map((n) => h("li", {}, chip(n.severity, n.severity === "action" ? "weak" : ""),
        n.topic ? link("#/t/" + n.topic, n.topic) : "", " ", n.message, h("span", { class: "muted small" }, " · " + fmtDate(n.at))))),
      h("div", { class: "actions" }, h("button", { onclick: async () => { await api.post("notifications/ack", {}); rerender(); } }, "Mark all read"))));
  }
  const side = [];
  if (d.continue) {
    const c = d.continue, href = (c.kind === "concept" ? "#/c/" : "#/s/") + c.id + (c.kind === "source" && c.para ? "?p=" + c.para : "");
    out.push(h("a", { class: "card link", href }, h("div", { class: "muted small", text: "Continue where you left off" }),
      h("h3", { text: c.title }), h("div", { class: "small muted" }, c.kind + " · " + pct(c.progress) + " read" + (c.para ? " · at ¶" + c.para : "")), bar(c.progress)));
  }
  if (d.next.length) {
    out.push(h("h2", { text: "Suggested next" }),
      h("div", { class: "grid" }, d.next.map((r) => h("a", { class: "card link", href: "#/c/" + r.concept },
        h("h3", { text: r.title }), h("div", { text: r.summary || "" }), h("div", { class: "why", text: "Why: " + r.reasons.join("; ") })))));
  }
  out.push(h("h2", { text: "Topics" }));
  out.push(d.topics.length ? h("div", { class: "grid" }, d.topics.map((t) => h("a", { class: "card link", href: "#/t/" + t.id },
    h("h3", { text: t.title }),
    h("div", {}, chip(t.depth), chip(t.status), t.scheduled ? chip("recurring", "moderate") : null,
      t.changes_since_visit ? chip(t.changes_since_visit + " new since your visit", "moderate") : null),
    h("div", { class: "small muted" }, `${t.concepts} concepts · ${t.claims} conclusions · ${t.open_questions} open questions`),
    h("div", { class: "small" }, `You: ${t.read}/${t.concepts} concepts read`), bar(t.concepts ? t.read / t.concepts : 0))))
    : h("p", { class: "muted" }, "No topics yet. Ask Claude or Codex: “Start researching …”."));
  if (d.due.length) side.push(h("div", { class: "panel" }, h("h3", { text: "Worth revisiting" }),
    h("ul", { class: "plain" }, d.due.map((x) => h("li", {}, link("#/c/" + x.concept, x.title), h("span", { class: "muted small" }, " · due " + x.due))))));
  side.push(sessionStarter(null));
  setView(h("div", { class: "cols" }, h("div", {}, out), h("aside", {}, side)));
}
function sessionStarter(topic) {
  const box = h("div", { class: "panel" }, h("h3", { text: "Start a learning session" }),
    h("p", { class: "small muted", text: "A short, skippable list chosen from what you haven't read, what you marked interesting or confusing, and what's due." }));
  const row = h("div", { class: "actions" });
  for (const m of [5, 15, 30, 60]) row.append(h("button", { onclick: async () => {
    const s = await api.post("sessions", { minutes: m, topic }); LS.set("session", s.id);
    if (!s.items.length) return toast("Nothing to suggest right now");
    location.hash = "#/session/" + s.id; } }, m + " min"));
  box.append(row); return box;
}

// ------------------------------------------------------------------ topic
async function topicView(id, tab) {
  currentTopic = id;
  const d = await api.get("topic/" + encodeURIComponent(id));
  const t = d.topic;
  LS.set("tab:" + id, tab);
  const conceptById = Object.fromEntries(d.concepts.map((c) => [c.id, c]));
  const head = [h("div", { class: "crumbs" }, link("#/", "Home"), " › topic"),
    h("h1", { text: t.title }),
    t.objective ? h("p", { class: "lede", text: t.objective }) : null,
    h("div", {}, chip(t.depth), chip(t.status), t.schedule && t.schedule.enabled ? chip("recurring: " + t.schedule.cron, "moderate") : null,
      chip("last researched " + fmtDate(t.last_investigated)))];
  const tabs = [["overview", "Overview"], ["concepts", `Concepts (${d.concepts.length})`], ["conclusions", `Conclusions (${d.claims.length})`],
    ["unknowns", `Unknowns (${d.unknowns.open_questions.length})`], ["sources", `Sources (${d.sources.length})`], ["activity", "Activity"]];
  const tabbar = h("div", { class: "tabs", role: "tablist" }, tabs.map(([k, label]) =>
    h("button", { class: tab === k ? "on" : "", role: "tab", onclick: () => { location.hash = `#/t/${id}?tab=${k}`; } }, label)));
  let body;
  if (tab === "concepts") body = conceptMap(d, conceptById);
  else if (tab === "conclusions") body = claimsList(d.claims, conceptById);
  else if (tab === "unknowns") body = unknownsView(d);
  else if (tab === "sources") body = sourcesList(d.sources);
  else if (tab === "activity") body = activityView(d);
  else body = overviewTab(d, conceptById);
  const side = [progressPanel(d), sessionStarter(id),
    h("div", { class: "panel" }, h("h3", { text: "Ask the researchers" }),
      h("p", { class: "small muted", text: "Questions go into this topic's research queue; the next research run picks them up." }),
      h("div", { class: "actions" },
        h("button", { onclick: () => modal("Your question", "", "What do you want to find out?", (x) => x && ask("question", x, { topic: id }), "", false) }, "Ask a question"),
        h("button", { onclick: () => modal("What looks missing?", "", "A gap you noticed", (x) => x && ask("gap", x, { topic: id }), "", false) }, "Report a gap")))];
  setView(...head, tabbar, h("div", { class: "cols" }, h("div", {}, body), h("aside", {}, side)));
}
function progressPanel(d) {
  const n = d.concepts.length, read = d.concepts.filter((c) => ["read", "practised", "shows understanding", "self-reported known"].includes(c.inferred.status)).length;
  const confused = d.concepts.filter((c) => c.inferred.status === "needs another look").length;
  return h("div", { class: "panel" }, h("h3", { text: "Your progress here" }),
    h("div", { class: "small" }, `${read} of ${n} concepts read or known` + (confused ? ` · ${confused} to look at again` : "")), bar(n ? read / n : 0),
    h("div", { class: "small muted mt" }, `${d.highlights} highlights · `, link("#/highlights", "see all")));
}
function overviewTab(d, conceptById) {
  const out = [];
  if (d.changes.items.length && d.changes.since) {
    out.push(h("div", { class: "panel notice" }, h("h3", { text: `New since your last visit (${fmtDate(d.changes.since)})` }),
      h("ul", { class: "plain" }, d.changes.items.slice(0, 8).map((c) => h("li", { class: "small" }, c.summary, h("span", { class: "muted" }, " · " + fmtDate(c.at))))),
      d.changes.items.length > 8 ? h("p", { class: "small muted" }, `…and ${d.changes.items.length - 8} more in Activity.`) : null,
      h("div", { class: "actions" }, h("button", { onclick: async () => { await api.post(`topic/${d.topic.id}/seen`, {}); rerender(); } }, "Mark as seen"))));
  } else if (!d.changes.since) {
    api.post(`topic/${d.topic.id}/seen`, {}).catch(() => {}); // first visit: start counting from now
  }
  out.push(h("div", { class: "ai-label", text: "Orientation · written by the research agent from the evidence" }));
  out.push(h("div", { class: "prose", "data-hl-scope": "", dataset: { kind: "overview", id: d.topic.id }, html: d.overview_html || "<p>No orientation yet.</p>" }));
  if (d.recommendations.length) {
    out.push(h("h2", { text: "Start here" }), h("div", { class: "grid" }, d.recommendations.map((r) =>
      h("a", { class: "card link", href: "#/c/" + r.concept }, h("h3", { text: r.title }), h("div", { text: r.summary || "" }),
        h("div", { class: "why", text: r.reasons.join("; ") })))));
  }
  const unknown = d.unknowns.open_questions.slice(0, 4);
  if (unknown.length) out.push(h("h2", { text: "Still unknown" }), h("ul", {}, unknown.map((q) => h("li", {}, q.text, " ", q.asked_by === "user" ? chip("you asked") : null))),
    link(`#/t/${d.topic.id}?tab=unknowns`, "All open questions →"));
  setTimeout(() => api.get("highlights?topic=" + d.topic.id).then((r) => {
    const scope = view.querySelector('[data-kind="overview"]');
    if (scope) applyHighlights(scope, r.highlights.filter((x) => x.target_kind === "overview"), highlightMenu);
  }), 0);
  return out;
}
function conceptCard(c) {
  return h("a", { class: "card link", href: "#/c/" + c.id },
    h("h3", { text: c.title }), h("div", { class: "small", text: c.summary || "" }),
    h("div", { class: "mt" }, chip(c.inferred.status, statusClass(c.inferred.status)),
      c.interest === "high" ? chip("★ interesting", "moderate") : null,
      c.prerequisites.length ? chip("builds on " + c.prerequisites.length) : null),
    c.progress && !c.completed ? bar(c.progress) : null);
}
function conceptMap(d, byId) {
  const names = ["Foundations", "Builds on the foundations", "Further", "Advanced"];
  const out = [h("p", { class: "muted small", text: "Concepts arranged by what they build on. Read in any order; cards show your state (observed or self-reported, never assumed)." })];
  d.layers.forEach((layer, i) => out.push(h("div", { class: "layer" }, h("div", { class: "layer-title", text: names[i] || `Level ${i + 1}` }),
    h("div", { class: "grid" }, layer.map((cid) => byId[cid]).filter(Boolean).map(conceptCard)))));
  if (!d.concepts.length) out.push(h("p", { class: "muted", text: "No concepts yet." }));
  return out;
}
function evidenceItem(e, against) {
  return h("div", { class: "ev" + (against ? " against" : "") },
    e.quote ? h("q", { text: e.quote }) : h("span", { class: "muted", text: e.note || "(observation)" }),
    e.verified === false ? chip("unverified quote", "weak") : null,
    h("span", { class: "src" }, against ? "Against · " : "", link("#/s/" + e.source + (e.para ? "?p=" + e.para : ""), e.source_title || e.source),
      e.locator ? " · " + e.locator : "", " · ", chip(e.source_category || "source"),
      e.source_url ? h("span", {}, " · ", ext(e.source_url, "original ↗")) : null),
    e.note && e.quote ? h("div", { class: "small muted" }, h("span", { class: "chip ai" }, "AI note"), " " + e.note) : null);
}
function claimItem(c, byId) {
  return h("div", { class: "claim" },
    h("div", { class: "text", text: c.text }),
    h("div", {}, chip(c.strength, c.strength), chip(c.kind), (c.concepts || []).filter((x) => byId && byId[x]).map((x) => link("#/c/" + x, byId[x].title, "chip"))),
    c.uncertainty ? h("div", { class: "small muted" }, "Uncertainty: " + c.uncertainty) : null,
    h("details", {}, h("summary", {}, `Evidence (${c.support.length} for` + (c.counter.length ? `, ${c.counter.length} against` : "") + ")"),
      c.support.map((e) => evidenceItem(e, false)), c.counter.map((e) => evidenceItem(e, true)),
      h("div", { class: "small muted" }, "Last verified " + (c.last_verified || "—") + " · " + c.id)));
}
function claimsList(claims, byId) {
  if (!claims.length) return [h("p", { class: "muted", text: "No conclusions yet." })];
  const out = [h("p", { class: "muted small", text: "Strength is the agent's assessment of the evidence, not a probability. Open a claim to see the exact passages it rests on." })];
  for (const s of ["strong", "moderate", "weak", "contested", "unsupported"]) {
    const g = claims.filter((c) => c.strength === s); if (!g.length) continue;
    out.push(h("h2", { text: s[0].toUpperCase() + s.slice(1) }), h("div", { class: "panel" }, g.map((c) => claimItem(c, byId))));
  }
  return out;
}
function unknownsView(d) {
  const claimById = Object.fromEntries(d.claims.map((c) => [c.id, c]));
  const out = [h("h2", { text: "Open research questions" }),
    d.unknowns.open_questions.length ? h("ul", { class: "plain" }, d.unknowns.open_questions.map((q) => h("li", {}, q.text, " ",
      chip(q.status), chip(q.origin), q.perspective ? chip(q.perspective) : null, q.asked_by === "user" ? chip("you asked", "moderate") : null)))
      : h("p", { class: "muted", text: "Nothing open." })];
  if (d.unknowns.contested.length) out.push(h("h2", { text: "Contested" }), h("div", { class: "panel" }, d.unknowns.contested.map((id) => claimItem(claimById[id]))));
  if (d.unknowns.weak.length) out.push(h("h2", { text: "Weakly supported or hypothetical" }), h("div", { class: "panel" }, d.unknowns.weak.map((id) => claimItem(claimById[id]))));
  if (d.answered.length) out.push(h("h2", { text: "Answered" }), h("ul", { class: "plain" }, d.answered.map((q) => h("li", {}, h("strong", { text: q.text }),
    h("div", { class: "small", text: q.result || "" })))));
  return out;
}
function sourcesList(sources) {
  const have = sources.filter((s) => s.access !== "wanted"), wanted = sources.filter((s) => s.access === "wanted");
  const out = [h("ul", { class: "plain" }, have.map((s) => h("li", {}, h("div", { class: "row" }, link("#/s/" + s.id, s.title), chip(s.category),
    s.evidence ? chip(s.evidence + " evidence") : null, s.extraction !== "ok" ? chip(s.extraction, "weak") : null,
    s.progress ? chip("you: " + pct(s.progress)) : null, h("span", { class: "spacer" }), s.url ? ext(s.url, "original ↗") : null))))];
  if (wanted.length) out.push(h("h2", { text: "To acquire" }), h("p", { class: "small muted", text: "Books and materials worth getting (legal copies only). Add a copy with: kw source add --file …" }),
    h("ul", { class: "plain" }, wanted.map((s) => h("li", {}, h("strong", { text: s.title }), s.why ? h("div", { class: "small", text: s.why }) : null))));
  return out;
}
function activityView(d) {
  return [h("h2", { text: "Recent research runs" }),
    h("ul", { class: "plain" }, d.runs.map((r) => h("li", {}, h("strong", { text: fmtDate(r.started) }), " ", chip(r.status),
      r.stats ? h("span", { class: "small" }, ` +${r.stats.sources_added || 0} sources, +${r.stats.evidence_added || 0} evidence, +${r.stats.claims_added || 0} claims, ${r.stats.claims_revised || 0} revised`) : null,
      r.stop_reason ? h("div", { class: "small muted", text: "Stopped: " + r.stop_reason }) : null))),
    h("h2", { text: "Changes" }),
    h("ul", { class: "plain" }, d.changes.items.map((c) => h("li", { class: "small" }, c.summary, h("span", { class: "muted" }, " · " + fmtDate(c.at)),
      c.detail ? h("div", { class: "muted", text: "Why: " + c.detail }) : null)))];
}

// ------------------------------------------------------------------ concept
async function conceptView(id) {
  const d = await api.get("concept/" + encodeURIComponent(id));
  const c = d.concept;
  currentTopic = (c.topics || [])[0] || currentTopic;
  const depth = LS.get("depth", "read");
  const st = d.state;
  const out = [h("div", { class: "crumbs" }, link("#/", "Home"), " › ", currentTopic ? link("#/t/" + currentTopic + "?tab=concepts", currentTopic) : "", " › concept"),
    h("h1", { text: c.title }),
    h("p", { class: "lede", text: c.summary || "" }),
    h("div", {}, chip(st.inferred.status, statusClass(st.inferred.status)), h("span", { class: "small muted" }, " " + st.inferred.basis)),
    h("div", { class: "depth", role: "group", "aria-label": "Depth" }, [["glance", "Glance"], ["read", "Read"], ["deep", "Deep"]].map(([k, l]) =>
      h("button", { class: depth === k ? "on" : "", onclick: () => { LS.set("depth", k); rerender(); } }, l)))];
  const article = h("article", { "data-hl-scope": "", dataset: { kind: "concept", id: c.id } });
  if (depth === "glance") {
    const key = d.claims.slice(0, 4);
    article.append(key.length ? h("div", {}, h("h2", { text: "Key points" }), h("ul", {}, key.map((x) => h("li", {}, x.text, " ", chip(x.strength, x.strength))))) :
      h("p", { class: "muted", text: "Switch to Read for the explanation." }));
  } else {
    article.append(h("div", { class: "ai-label", text: "Explanation · AI-written from the evidence · " + fmtDate(c.updated) }),
      h("div", { class: "prose", "data-section": "Explanation", html: d.explanation_html || "<p>No explanation yet.</p>" }));
    if (d.alternative_html) article.append(h("h2", { text: "Another way to see it" }), h("div", { class: "prose", "data-section": "Alternative explanation", html: d.alternative_html }));
    if (depth === "deep" && d.details_html) article.append(h("h2", { text: "In depth" }), h("div", { class: "prose", "data-section": "Details", html: d.details_html }));
  }
  out.push(article);
  if (depth === "deep" && d.claims.length) out.push(h("h2", { text: "What the evidence says" }), h("div", { class: "panel" }, d.claims.map((x) => claimItem(x))));
  if (depth !== "glance" && d.prompts.length) out.push(h("h2", { text: "Think it through" }),
    h("p", { class: "small muted", text: "Optional. Writing an answer is the best evidence that you understand — it's kept as your own words, not graded." }),
    d.prompts.map((p) => promptBox(c.id, p, d.answers.filter((a) => a.prompt === p.text))));
  out.push(h("div", { class: "panel" },
    h("div", { class: "actions" }, h("span", { class: "label" }, "How well do you know this?"),
      [["new", "New to me"], ["heard", "Heard of it"], ["familiar", "Familiar"], ["known", "I know this — stop suggesting it"], ["confused", "I'm confused"]].map(([v, l]) =>
        h("button", { class: (st.self_report || {}).value === v ? "on" : "", onclick: async () => {
          await api.post("mark", { concept: c.id, value: v });
          toast(v === "known" ? "Noted — it won't be suggested again" : v === "confused" ? "Noted — it will come back soon. Want another explanation?" : "Noted");
          if (v === "confused") setTimeout(() => modal("Ask for another explanation?", "", "Optional: what's unclear", (t) => ask("explain-differently", t, { concept: c.id })), 300);
          rerender(); } }, l))),
    h("div", { class: "actions" }, h("span", { class: "label" }, "Want more?"),
      h("button", { class: (st.interest || {}).value === "high" ? "on" : "", onclick: async () => { await api.post("interest", { concept: c.id, value: (st.interest || {}).value === "high" ? "normal" : "high" }); rerender(); } }, "★ Interesting"),
      h("button", { onclick: () => modal("Go deeper on " + c.title, "", "What would you like to know more about? (optional)", (t) => ask("deeper", t, { concept: c.id })) }, "Go deeper"),
      h("button", { onclick: () => modal("Explain it differently", "", "What didn't work in this explanation? (optional)", (t) => ask("explain-differently", t, { concept: c.id })) }, "Explain differently"),
      h("button", { onclick: () => modal("What doesn't convince you?", "", "Your doubt", (t) => ask("challenge", t, { concept: c.id })) }, "I'm not convinced"),
      h("button", { onclick: () => modal("Your question", "", "Ask anything about " + c.title, (t) => t && ask("question", t, { concept: c.id }), "", false) }, "Ask")),
    st.observed.completed_at ? h("div", { class: "small muted" }, "You finished reading this on " + fmtDate(st.observed.completed_at) +
      (st.revisit && st.revisit.due ? ` · suggested revisit ${st.revisit.due}` : ""),
      st.revisit && st.revisit.due ? h("button", { class: "ml", onclick: async () => { await api.post("revisited", { concept: c.id }); toast("Next revisit pushed out"); rerender(); } }, "I revisited it") : null)
      : h("button", { onclick: async () => { await api.post("progress", { kind: "concept", id: c.id, fraction: 1, depth, completed: true }); toast("Marked as read"); rerender(); } }, "I've read this")));
  const side = [];
  const nav = (title, items) => items.length ? h("div", { class: "panel" }, h("h3", { text: title }), h("ul", { class: "plain" }, items.map((x) =>
    h("li", {}, x.exists === false ? h("span", { class: "muted", text: x.title }) : link("#/c/" + x.id, x.title), x.rel ? h("span", { class: "muted small" }, " · " + x.rel) : null,
      x.inferred ? h("div", {}, chip(x.inferred, statusClass(x.inferred))) : null)))) : null;
  side.push(nav("Builds on", d.prerequisites), nav("Leads to", d.leads_to), nav("Related", d.related));
  if (d.sources.length) side.push(h("div", { class: "panel" }, h("h3", { text: "Sources" }), h("ul", { class: "plain" }, d.sources.map((s) =>
    h("li", {}, link("#/s/" + s.id, s.title), " ", chip(s.category))))));
  if (d.questions.length) side.push(h("div", { class: "panel" }, h("h3", { text: "Questions about this" }), h("ul", { class: "plain" }, d.questions.map((q) =>
    h("li", { class: "small" }, q.text, " ", chip(q.status, q.status === "answered" ? "strong" : ""), q.result ? h("div", { class: "muted", text: q.result }) : null)))));
  setView(h("div", { class: "cols" }, h("div", {}, out), h("aside", {}, side)));
  applyHighlights(article, d.highlights, highlightMenu);
  tracker = new Tracker("concept", c.id, article, depth);
}
function promptBox(cid, p, answers) {
  const ta = h("textarea", { placeholder: "Your answer, in your own words" });
  return h("div", { class: "prompt" }, h("div", { class: "kind", text: p.kind }), h("div", { text: p.text }), ta,
    h("div", { class: "actions" }, h("button", { onclick: async () => {
      if (!ta.value.trim()) return ta.focus();
      await api.post("answers", { concept: cid, prompt: p.text, kind: p.kind, text: ta.value }); toast("Saved — ask your agent to review it if you like"); rerender(); } }, "Save my answer")),
    answers.length ? h("div", { class: "answers" }, answers.map((a) => h("div", {}, h("blockquote", { text: a.text }),
      h("div", { class: "small muted" }, fmtDate(a.created) + " · " + (a.review && a.review.assessment ? "reviewed: " + a.review.assessment + (a.review.note ? " — " + a.review.note : "") : "not reviewed"))))) : null);
}

// ------------------------------------------------------------------ source
async function sourceView(id, jump) {
  const d = await api.get("source/" + encodeURIComponent(id));
  const s = d.source;
  currentTopic = (s.topics || [])[0] || currentTopic;
  const evByPara = {};
  for (const e of d.evidence) if (e.para) (evByPara[e.para] = evByPara[e.para] || []).push(e);
  const text = h("div", { class: "src-text", "data-hl-scope": "", dataset: { kind: "source", id: s.id } },
    d.paragraphs.map((p, i) => { const n = d.start + i;
      return h("p", { dataset: { para: n }, id: "p" + n, class: evByPara[n] ? "has-ev" : "", title: evByPara[n] ? "Used as evidence: " + evByPara[n].map((e) => e.id).join(", ") : null },
        h("span", { class: "pn", text: "¶" + n }), p); }));
  const o = d.state.observed;
  const resumeAt = jump || (o.para && o.progress < 0.98 ? o.para : null);
  const out = [h("div", { class: "crumbs" }, link("#/", "Home"), " › ", currentTopic ? link("#/t/" + currentTopic + "?tab=sources", currentTopic) : "", " › source"),
    h("h1", { text: s.title }),
    h("div", {}, chip(s.category), s.authors && s.authors.length ? chip(s.authors.join(", ")) : null, s.published ? chip("published " + String(s.published).slice(0, 10)) : null,
      chip("retrieved " + fmtDate(s.retrieved)), s.rights && s.rights !== "unknown" ? chip(s.rights) : null),
    s.canonical_url ? h("p", { class: "small" }, ext(s.canonical_url, s.canonical_url)) : null,
    s.assessment ? h("p", { class: "small" }, h("span", { class: "chip ai" }, "AI assessment"), " " + s.assessment) : null,
    d.summary_html ? h("div", { class: "panel" }, h("div", { class: "ai-label", text: "Summary · AI-written" }), h("div", { class: "prose", html: d.summary_html })) : null];
  if (resumeAt && !jump) out.push(h("div", { class: "banner" }, `Resumed where you left off (¶${resumeAt}). `, h("a", { href: "#", onclick: (e) => { e.preventDefault(); window.scrollTo(0, 0); } }, "Back to the top")));
  if (d.evidence.length) out.push(h("details", { class: "panel" }, h("summary", {}, `Evidence the research took from this source (${d.evidence.length})`),
    h("ul", { class: "plain" }, d.evidence.map((e) => h("li", { class: "small" }, e.para ? link("#/s/" + s.id + "?p=" + e.para, "¶" + e.para) : "", " “" + (e.quote || e.note || "") + "”",
      e.claims.length ? h("span", { class: "muted" }, " → " + e.claims.join(", ")) : null)))));
  if (!d.paragraphs.length) out.push(h("p", { class: "muted", text: s.extraction === "ok" ? "No text." : `No stored text (${s.extraction}${s.extraction_note ? ": " + s.extraction_note : ""}).` }));
  else out.push(h("p", { class: "small muted", text: "Text as extracted from the original (formatting may be lost). Select any passage to highlight, annotate or question it." }), text);
  if (d.total_paragraphs > d.start - 1 + d.paragraphs.length) out.push(h("p", { class: "muted small", text: `Showing ${d.paragraphs.length} of ${d.total_paragraphs} paragraphs.` }));
  setView(...out);
  applyHighlights(text, d.highlights, highlightMenu);
  if (resumeAt) { const el = document.getElementById("p" + resumeAt); if (el) { if (jump) el.classList.add("target"); setTimeout(() => el.scrollIntoView({ block: "start" }), 50); } }
  tracker = new Tracker("source", s.id, text, "read");
}

// ------------------------------------------------------------------ highlights & export
async function highlightsView() {
  const d = await api.get("highlights");
  const selected = new Set();
  const conceptSel = new Set();
  const status = h("div", { class: "files" });
  const byTopic = {};
  for (const x of d.highlights) (byTopic[(x.topics || ["other"])[0]] = byTopic[(x.topics || ["other"])[0]] || []).push(x);
  const conceptIds = [...new Set(d.highlights.filter((x) => x.target_kind === "concept").map((x) => x.target_id))];
  const out = [h("h1", { text: "Highlights" }),
    h("p", { class: "muted", text: "Your highlights and notes. Exact source quotations stay quotations; passages you highlighted in AI-written explanations are labelled as such." })];
  if (!d.highlights.length) out.push(h("p", { class: "muted", text: "No highlights yet — select text in any concept or source." }));
  for (const [topic, items] of Object.entries(byTopic)) {
    out.push(h("h2", {}, link("#/t/" + topic, topic)));
    out.push(h("div", { class: "panel" }, items.map((x) => {
      const cb = h("input", { type: "checkbox", onchange: (e) => (e.target.checked ? selected.add(x.id) : selected.delete(x.id)) });
      const target = x.target_kind === "source" ? "#/s/" + x.target_id + (x.locator ? "?p=" + x.locator.replace("¶", "") : "") : x.target_kind === "concept" ? "#/c/" + x.target_id : "#/t/" + x.target_id;
      return h("div", { class: "hl-item" }, cb, h("div", {}, h("q", { text: x.quote }),
        h("div", { class: "small muted" }, chip(x.quote_origin, x.target_kind === "source" ? "strong" : "ai"), link(target, x.target_id), x.locator ? " " + x.locator : "", " · " + fmtDate(x.created),
          x.exported ? " · exported " + fmtDate(x.exported) : ""),
        x.note ? h("div", { class: "small" }, h("strong", {}, "My note: "), x.note) : null,
        h("div", { class: "actions" }, h("button", { onclick: () => highlightMenu(x) }, x.note ? "Edit note" : "Add note"))));
    })));
  }
  if (d.highlights.length) {
    const cbox = conceptIds.length ? h("div", {}, h("p", { class: "small", text: "Also create concept notes (atomic, Zettelkasten-style) for:" }),
      conceptIds.map((cid) => h("label", { class: "chip" }, h("input", { type: "checkbox", onchange: (e) => (e.target.checked ? conceptSel.add(cid) : conceptSel.delete(cid)) }), " " + cid))) : null;
    out.push(h("div", { class: "panel" }, h("h2", { text: "Export to Obsidian" }),
      h("p", { class: "small muted", text: "Writes Markdown with YAML frontmatter and wikilinks to the export folder (not your vault directly). Notes you edited after an earlier export are not overwritten." }),
      cbox, h("div", { class: "actions" }, h("button", { class: "primary", onclick: async () => {
        if (!selected.size && !conceptSel.size) return toast("Select highlights or concepts first");
        try { const r = await api.post("export", { highlights: [...selected], concepts: [...conceptSel] });
          status.textContent = r.dir + "\n" + r.files.map((f) => `${f.action.padEnd(9)} ${f.path}${f.note ? "  (" + f.note + ")" : ""}`).join("\n");
          toast(`Exported ${r.files.length} note(s)`); } catch (e) { toast(e.message); } } }, "Export selected")), status));
  }
  setView(...out);
}
async function questionsView() {
  const d = await api.get("questions");
  setView(h("h1", { text: "Your questions" }),
    h("p", { class: "muted", text: "Everything you asked, challenged or wanted deeper while reading. Each one is a research question the next run can pick up." }),
    d.questions.length ? h("div", { class: "panel" }, h("ul", { class: "plain" }, d.questions.map((q) => h("li", {},
      h("div", { class: "row" }, h("strong", { text: q.text }), h("span", { class: "spacer" }), chip(q.status, q.status === "answered" ? "strong" : "")),
      h("div", { class: "small muted" }, link("#/t/" + q.topic, q.topic), (q.concepts || []).map((c) => [" · ", link("#/c/" + c, c)]), " · asked " + fmtDate(q.created),
        q.last_evaluated ? " · last researched " + fmtDate(q.last_evaluated) : ""),
      q.result ? h("div", { class: "small", text: "Answer: " + q.result }) : null))))
      : h("p", { class: "muted", text: "None yet." }));
}
async function searchView(q) {
  const d = await api.get("search?q=" + encodeURIComponent(q));
  const href = (r) => r.kind === "concept" ? "#/c/" + r.id : r.kind === "source" ? "#/s/" + r.id : r.kind === "claim" ? (r.concepts[0] ? "#/c/" + r.concepts[0] : "#/t/" + r.topic + "?tab=conclusions") : "#/highlights";
  setView(h("h1", { text: `Search: ${q}` }), d.results.length ? h("ul", { class: "plain" }, d.results.map((r) =>
    h("li", {}, chip(r.kind), link(href(r), r.title), r.snippet ? h("div", { class: "small muted", text: r.snippet }) : null))) : h("p", { class: "muted", text: "No matches." }));
}

// ------------------------------------------------------------------ sessions
async function sessionView(id) {
  const s = await api.get("sessions/" + id);
  LS.set("session", s.id);
  setView(h("h1", { text: `Learning session · ${s.minutes} min` }),
    h("p", { class: "muted", text: s.note }),
    h("div", { class: "panel" }, h("ol", {}, s.items.map((it, i) => h("li", { class: "step" },
      h("div", { class: "row" }, link("#/c/" + it.concept, it.title), chip(it.depth), chip("~" + it.minutes + " min"), it.done ? chip("done", "strong") : null),
      h("div", { class: "small muted", text: it.reason }))))),
    h("div", { class: "actions" }, h("button", { class: "primary", onclick: () => { const first = s.items.find((x) => !x.done) || s.items[0];
      if (first) { LS.set("depth", first.depth); location.hash = "#/c/" + first.concept; } } }, "Start"),
      h("button", { onclick: () => { LS.set("session", null); location.hash = "#/"; } }, "End session")));
}
async function renderSessionBar() {
  const barEl = document.getElementById("session-bar");
  const sid = LS.get("session", null);
  const m = location.hash.match(/^#\/c\/([^?]+)/);
  if (!sid || !m) { barEl.hidden = true; return; }
  let s; try { s = await api.get("sessions/" + sid); } catch { barEl.hidden = true; return; }
  const cid = decodeURIComponent(m[1]);
  const idx = s.items.findIndex((x) => x.concept === cid);
  if (idx < 0) { barEl.hidden = true; return; }
  const next = s.items.slice(idx + 1).find((x) => !x.done);
  barEl.replaceChildren(h("span", {}, `Session · ${idx + 1} of ${s.items.length}`), h("span", { class: "spacer" }),
    h("button", { onclick: async () => { await api.post(`sessions/${sid}/step`, { index: idx, done: true });
      if (next) { LS.set("depth", next.depth); location.hash = "#/c/" + next.concept; } else { toast("Session complete"); LS.set("session", null); location.hash = "#/"; } } },
      next ? "Done · next →" : "Done · finish"),
    h("button", { onclick: () => { location.hash = "#/session/" + sid; } }, "Overview"),
    h("button", { onclick: () => { LS.set("session", null); barEl.hidden = true; } }, "Leave"));
  barEl.hidden = false;
}

route();
