# Trellis paper plan

**Venue.** FSE 2027 Tool Demonstrations: submission 26 Jan 2027, notification 17 Mar, camera-ready 2 Apr.
ACM format, 4 pages of text, figures and tables plus 1 page of references, a walkthrough appendix and a screencast.
Fallback: ICSME 2027 Tool Demo / NIER (IEEE proceedings, deadline expected spring 2027). The 4-page
`paper/workshop/` draft targets an archival ICSE 2028 workshop (LLM4Code publishes ACM proceedings).

**Story (one line).** A rule written in an instruction file is a request, not a check. Trellis finds the
written rules nothing enforces, turns them into checks, and blocks only new debt.

## Experiments

| RQ | Question | Status | Result file |
|---|---|---|---|
| RQ1a | Share of instruction statements that are checkable, and enforced, over 295 random AIDev repos | done (PR #3) | `results/audit_v1.json` |
| RQ1b | Same over the 761 AIDev repos with the most agent PRs whose instruction files still exist | done: 2,303 checkable of 148,837 statements; 142 enforced (6.2%) | `results/audit_v2/summary.json` |
| RQ1b' | RQ1b re-run with the PR #5 classifier (fresh clones, 761 repos, 3 without instruction files dropped) | done: 1,787 checkable of 149,530 statements; 116 enforced (6.5%) | `results/audit_v3/summary.json` |
| RQ1c | Precision of audit's checkable labels | spot check done: 58/120 correct (48%); blinded 2-person audit of 200: sample and sheets in `annotation/`, Devin's labels sealed, second annotator pending; on re-run, 27 of 62 wrong labels dropped, 4 of 58 right labels dropped, unchanged labels 54/80 correct (`results/audit_v3/spotcheck_rescore.json`) | `results/audit_v2/precision_spotcheck.json` |
| RQ2 | Do agent PRs break enforced rules less often than enforceable-but-unenforced ones? Run the emitted check on each repo's agent-PR added lines; repo fixed effects | not run; needs RQ1c precision >= 0.8 on the rules used | - |
| RQ3 | Built-in scan checks on agent PRs: flags/100 PRs, undone rate vs baseline, false alarms/100 PRs, kill rule | done (PR #3) | `results/scan_v1.json` |
| RQ3b | Trellis vs an LLM reviewer (Claude Haiku) on the same PRs | done (PR #3) | `results/llm_v1.json` |
| RQ4 | Does scan debt grow across a repo's successive agent PRs (what the ratchet prevents)? | not run | - |

**Blocking finding.** The spot check shows audit's classifier is the weak point. Common errors: inverted
"use X instead of Y" (bans X), placeholder names (`new TypeName()`), Python rules mapped to ESLint, CLI flags
mapped to `no-restricted-imports`, and any sentence with "scope" mapped to the scope check. Next step: fix
these in `audit.py` (a separate product PR), re-run RQ1b, then do the blinded audit. No RQ1 percentage goes
into the paper until its precision is measured.

## Figures (tool-demo paper)

1. Architecture: instruction files -> audit (enforced / enforceable / judgment) -> emitted config; PR diff -> scan -> ratchet check -> one PR comment. TikZ.
2. RQ1: per-repo stacked bars (judgment, enforceable, enforced), log scale, 761 repos sorted by rule count; inset 100% bar of the checkable slice.
3. RQ3 (exists): per-check undone rate vs baseline and false alarms/100 PRs, kill-rule lines drawn.
4. RQ3b (exists): Trellis vs LLM reviewer, flags vs undone rate.
5. Screenshot: the Action's comment on a live demo PR.
6. RQ4 (if run): median scan debt per repo vs PR index, with the ratchet's flat line for contrast.

## Demo / screencast (about 3 min)

`trellis audit` on a real repo -> `--write` emits ESLint/Ruff config -> `trellis scan` on a sloppy agent PR ->
`trellis check --base main` fails only on the new hit -> the Action's single PR comment.
