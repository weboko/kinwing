# Roadmap (deliberately deferred)

Ordered by expected value to the user, not novelty.

1. **Live agent shakedown** (OQ-2, OQ-3). Run scheduled research with real Claude and Codex
   agents for a couple of weeks; tighten the protocol and the brief from what they actually do.
   *Depends on:* an ai-box install.
2. **Read-it-later inbox.** `kw source add URL --topic inbox` from the phone (a tiny
   endpoint in the reader, or a share target); the next run triages it into topics.
   *Value:* captures material the user finds. *Depends on:* reader auth when remote.
3. **Search index** (ADR-0002 option 2): `runtime/index.sqlite` with FTS5, rebuilt from files;
   faster search and "where else is this concept discussed". Optional embeddings later for
   paraphrase-level duplicate detection.
4. **Highlights → recall items with FSRS** (opt-in). Turn a highlight into a question/cloze and
   schedule it with py-fsrs; keep it separate from the exploratory reader.
   *Depends on:* real usage showing the user wants memorisation for some topics.
5. **Better concept map.** A small zoomable graph view (prerequisites and contrasts) in the
   reader. A lightweight version may reuse the create-report blueprint style, without coupling.
6. **Source acquisition helpers.** Library-catalogue lookups (Open Library) for the book
   acquisition list; DOI → open-access PDF via Unpaywall; arXiv ingestion with metadata.
7. **Notification delivery.** Optional push of `important`/`action` notifications (ntfy,
   email) behind the existing queue.
8. **Bidirectional Obsidian.** Read back edits to exported "My thoughts" sections as user
   annotations. Needs a careful merge story.
9. **MCP server** exposing the `kw` functions, for clients without shell access.
10. **Multi-user / sharing**: out of scope until there is a second user.
