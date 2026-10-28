# 0004 — Agents are the engine; kinwing is a CLI and skills

- Date: 2026-10-28 · Status: Accepted

## Context
Claude Code and Codex already search, read, reason and write well, with their own context
management and tools. STORM, Co-STORM and Letta implement LLM pipelines because they predate,
or don't assume, capable coding agents.

## Problem
How much of the research process should kinwing implement itself?

## Alternatives
1. A service that calls LLM APIs (a STORM-style pipeline). Needs API keys, which ai-box
   avoids because they break subscription logins; duplicates the agents; and cost becomes ours.
2. MCP server with tools. Good discoverability, but more moving parts and per-client config;
   the skills convention already works for both agents in ai-box.
3. **Skills plus a CLI.** The skill says *how* to research; the CLI keeps *state*, provenance
   and rules (ids, dedup, quote verification, budgets, history).

## Decision
Option 3. `kw` is deterministic and makes no model calls. Anything that needs judgement
(which sources, what a passage means, how strong a claim is, how to explain a concept) is the
agent's, guided by `knowledge-research/SKILL.md` and `references/research-run.md`.

## Rationale
- Works the same from Claude and Codex, interactively or under agent-orchestrator.
- Correctness lives where it can be tested: the suite (77 tests) runs without any LLM.
- The model can improve without code changes; the CLI's contract stays stable.

## Consequences
- Research quality depends on the agent following the protocol. The CLI enforces what it
  can: verbatim quotes, required reasons for revisions, budgets, no deletion.
- An MCP wrapper could later expose the same functions (ROADMAP).

## Reversibility
High. The CLI functions are a library; an MCP or HTTP API can call them.
