# 0013 — Stdlib-only Python with a built-in YAML subset

- Date: 2026-10-28 · Status: Accepted

## Context
The ai-box claude and box images have Python 3.12 without PyYAML; the codex image has no
Python at all. `pip install` into Ubuntu's system Python is blocked by PEP 668, and installs
inside a box are lost on rebuild.

## Alternatives
Bash + jq (painful for this much logic); Node (absent from the codex image too); a Go binary
(build pipeline); Python with vendored PyYAML; **Python stdlib only**.

## Decision
Stdlib only. `yamlio` always *writes* with its own emitter (block style, quoting anything
that could be mis-typed: dates, numbers, yes/no, `: `), whose output is standard YAML.
It *reads* with PyYAML when installed, else with a built-in parser for the subset the emitter
writes plus ordinary hand edits (comments, flow lists and maps, block scalars, lists of
maps). The test suite runs in both modes (`KW_YAML=builtin`) and checks both parsers agree.

## Consequences
YAML anchors, tags and multi-document files are not supported in hand edits. Codex-only
boxes need python3 (`--codex-python`).

## Reversibility
High.
