---
name: knowledge-learn
description: Helps the user learn and remember what their kinwing knowledge base holds — learning sessions in chat, the private reader, "what should I learn next", marking concepts as known or confusing, reviewing the user's own explanations, highlights, and exporting notes to Obsidian. Use when the user asks to learn, study, review, quiz themselves, explain or re-explain a researched concept, open the reader, says "I already understand X", "I don't understand this explanation", "what should I learn next", or "export my highlights to Obsidian".
---

# Knowledge learning (kinwing)

The knowledge base holds what the research agents found. This skill is about what **the user**
understands, which is a separate state: researching something never makes it the user's
knowledge. The CLI is the same `kw` as `knowledge-research` (its `bin/kw`; in ai-box
`/opt/box-context/skills/knowledge-research/bin/kw`).

The user's state lives in `$KW_HOME/learning/` and is theirs: change it only through `kw learn …`
commands that record what *they* said or did, never from your own guess.

| Kind | Examples | Recorded by |
|---|---|---|
| observed | opened, read to the end, wrote an answer | the reader, `kw learn …` on the user's behalf when they did it in chat |
| self-reported | "I know this", "I'm confused" | `kw learn mark C known|familiar|heard|new|confused` |
| inferred | "read", "practised", "shows understanding", "needs another look" | computed by rule, with its basis (`kw learn status`) |

## Intent → action

| User says… | Do |
|---|---|
| "What should I learn next?" | `kw learn next [--topic T]` → offer the top 2–3 with their reasons |
| "Teach me / let's study T for 15 minutes" | `kw learn session --minutes 15 --topic T`, then work through it in chat (below) |
| "Open the reader" | give the reader URL (`http://localhost:8765/`, via an SSH tunnel on a VPS: `ssh -L 8765:127.0.0.1:8765 host`) |
| "I already understand X, stop prioritizing it" | `kw learn mark X known` (it stops being suggested) |
| "I don't understand this explanation" | `kw learn mark X confused`; explain differently now (use the evidence: `kw show cl-…`, sources); if the kb lacks a better angle, queue `kw q add "Find another way to explain X: …" --topic T --origin learning --asked-by user` |
| "I'm not convinced that …" | queue a challenge question (`--origin learning --asked-by user --priority high`), show the evidence behind the claim, and investigate now if they want |
| "This is interesting, go deeper" | `kw learn interest X high` + a `--origin learning` question |
| "What did I ask?" | `kw learn questions` (status and answers of the user's questions) |
| "Review my answers" | `kw learn answers --pending`, then `kw learn review a-… --assessment sound|partial|misconception --note "…"` with specific, kind feedback |
| "Export my highlights to Obsidian" | `kw export obsidian --highlights all [--topic T] [--concepts c1,c2] [--out DIR]` → list the files |
| "What's new since I last looked?" | `kw changes --since 7d` and `kw notify list`; `kw notify ack` after reading them together |

## A learning session in chat

Not a lecture and not a quiz. For each item from `kw learn session` (or `kw learn next`):
1. Ask what they already know about it (one line). Skip ahead if they know it — and offer
   `kw learn mark C known`.
2. Explain at the depth they choose: glance (the concept's summary), read (its Explanation),
   deep (Details + the claims and their quoted evidence: `kw concept list`, `kw show C`, `kw show cl-…`).
   Build on the topic's `familiarity`. Cite sources when you state facts.
3. Offer one generative prompt from the concept's Prompts (explain in your words, predict,
   compare, apply, critique). If they answer, store their words verbatim
   (`kw learn answer C --prompt "…" --text "…"`), give honest, specific feedback, and record it
   (`kw learn review a-… --assessment … --note "…"`).
4. Let them steer: deeper, sideways to a related concept, a question for the researchers.
5. For each concept they actually worked through: `kw learn studied C --depth read|deep`.
   End with what they covered and one suggestion for next time. Don't assign homework.

Full spaced repetition is deliberately not used yet: concepts the user read or answered get
an expanding "worth revisiting" date (1, 3, 7, 21, 60, 150 days); confusing ones come back
the next day. `kw learn next` already accounts for it.

## Obsidian export

- Source notes (`Sources/<title>.md`): exact quotations as `>` quotes with `^h-…` block ids,
  the user's notes labelled **My note**, the AI summary in a collapsed callout marked AI-written.
- Concept notes (`Concepts/<title>.md`), only for concepts the user picks: **My thoughts**
  first (their annotations and answers), then the AI synthesis (callout), key evidence quotes
  linking to source notes, related concepts.
- A `Topics/<title>.md` map of what was exported. YAML frontmatter has `kw_id`, `tags`, `topics`.
- Default folder `$KW_EXPORT_DIR` (or `$KW_HOME/exports/obsidian`), never the vault itself unless
  the user points `--out` at it. Notes the user edited after an export are not overwritten
  (the new version goes to `.kinwing/pending/`) unless they say `--force`.

## Never

- Infer that the user knows something because they opened it, or because research covered it.
- Put the user's highlights, answers, questions or progress into a report or anything public.
- Grade or score the user numerically.
