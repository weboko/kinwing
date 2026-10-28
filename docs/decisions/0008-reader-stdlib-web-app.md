# 0008 — The reader: a stdlib server and a vanilla-JS app, in its own container

- Date: 2026-10-28 · Status: Accepted

## Alternatives
1. Reuse create-report templates as the reader. They are static, public-by-design snapshots;
   the reader is private, stateful and write-capable. Coupling them would blur the
   public/private line the brief insists on.
2. Obsidian as the reader. No progress tracking, no question capture into the research
   queue, no evidence navigation without plugins.
3. A framework app (React/Vite, FastAPI). Build tooling and dependencies for a single user.
4. **`http.server` + one HTML/CSS/JS bundle**, no build step and no dependencies.

## Decision
Option 4, run as `kinwing-reader` (the kinwing image; only `/knowledge` mounted; read-only
root filesystem; all capabilities dropped; port published on host loopback only). It can
also run in a box (`kw serve`).

Security: bind 127.0.0.1 by default; Host-header allowlist (DNS rebinding);
writes need `X-KW: 1` and a same-origin `Origin` (CSRF); optional `KW_READER_TOKEN` cookie;
strict CSP without inline styles or scripts; all agent and source text escaped
server-side (`mdrender`: no raw HTML, http(s)/in-app links only). Remote use goes through an
SSH tunnel or the user's existing protected tunnel, never through the public `~/www` site.

## Consequences
- Single user, no accounts. The token is a shared secret.
- The UI is deliberately plain; no graph visualisation (P2).

## Reversibility
High. The JSON API is the boundary; a richer front end can replace the static app.
