# RQ1c blinded label audit

Measures how often `trellis audit` is right when it calls an instruction-file statement *checkable* and proposes
a check for it. Two annotators label the same 200 statements independently; we report each annotator's
precision, their agreement (Cohen's kappa), and precision on the adjudicated labels.

## Sample

`build_sample.py` draws 200 checkable statements from the audit_v3 run (761 repos, classifier at PR #5
commit `7bbd6e3`): 100 Trellis-native rules, 70 ESLint, 30 Ruff, at most 3 per repo per tool, seed 20261123.
The 120 statements of the earlier unblinded spot check are excluded. Each row carries a tool weight
(pool size / sampled count); `tool_weighted_pct` reweights the three tools to their share of the eligible pool
(1,698 statements: the 1,787 checkable minus the 89 spot-check rows still present). It does not undo the
per-repo cap, which over-represents repos with few checkable statements, so report it as an approximation.

The sheets show the statement and the proposed check. They do not show whether the repo already enforces it,
and annotators do not see each other's sheet until both are done.

## Workflow

1. Each annotator fills a copy of `labels_template.csv` (or `labels_harshul.xlsx`, which has dropdowns)
   and saves it as `labels_<name>.csv`.
2. Devin's labels were finished first and are sealed: `labels_devin.sha256` holds the SHA-256 of
   `labels_devin.csv`, which is committed only after the other sheet is in. Check with `sha256sum -c labels_devin.sha256`.
3. Run `score.py`, discuss the disagreements it lists, write `labels_adjudicated.csv`, run `score.py` again.

## Columns to fill

- `checkable`: `y` if a deterministic check (lint rule, regex over added lines, import ban, path guard) could
  reliably catch violations of this statement; `n` if it needs judgment, runtime behaviour, or is not a rule.
- `check_matches`: does the proposed check implement the statement?
  - `y`: it flags violations of the statement and would not flag code the statement allows.
  - `partial`: right idea but clearly too broad or too narrow (e.g. bans every `any()` call when the rule is
    about one use of it).
  - `n`: wrong rule, wrong language, inverted, or the statement is not a rule at all.
  If `checkable` is `n`, `check_matches` is `n`.
- `notes`: optional, one line.

Judge the statement as written in the sheet; open the repo file only if the line is unreadable without context.

## Examples

| Statement | Proposed check | checkable | check_matches |
|---|---|---|---|
| Do not add `lodash` as a dependency. | eslint: no-restricted-imports (ban import lodash) | y | y |
| Never add test-only exports (`now`, `delay`). | trellis: ban `now` | n | n |
| Never use `any` when reading `list[0]` from the API. | eslint: @typescript-eslint/no-explicit-any | y | partial |
| Pre-existing bugs are out of scope. | trellis: scope | n | n |

## Scoring

`python score.py` reads `sample_key.jsonl`, `labels_harshul.csv`, `labels_devin.csv` and, if present,
`labels_adjudicated.csv` (same columns, disagreements resolved by discussion), and writes
`../results/audit_v3/precision_blinded.json`. Precision = share of rows with `check_matches = y`
(strict) or `y`/`partial` (lenient), per tool and weighted overall.
