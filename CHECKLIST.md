# Trellis project checklist

Status of rd0-trellis, the second rd0 tool. Jinx stops a team reviewing the same PR twice; Trellis stops it
reviewing the same mistake twice.

## 1. Origin

- [x] Source: Lauren Tan, *All Code Is Slop (Except Mine)*, AI Engineer CODE 2026 — move repeated corrections
      out of prose and into code, static checks and verification (the trust pyramid).
- [x] Four-reviewer panel (virality, competition, adoption, research): ship with changes. Mining review
      history demoted: only 2.6% of substantive human AIDev comments repeat an earlier one in the same repo
      (reviewer's measurement; to be re-run here). Scope corrections ("revert this file") are the most common
      checkable correction.

## 2. Tool (v0.1, this repo)

- [x] `trellis audit`: instruction-file discovery, rule extraction, enforced/enforceable/judgment, ESLint,
      Ruff, import-linter and `trellis.toml` emission; local path or `owner/repo`.
- [x] `trellis scan`: zero-config `scope`, `workaround-comment`, `bare-suppression`, `commented-out-code`;
      custom `[[rule]]` regexes; warn by default.
- [x] `trellis check`: net-count ratchet, `error` rules fail only when they get worse, remaining debt.
- [x] GitHub Action: one comment, edited in place, silent when clean, config from the base branch.
- [x] Tests on Python 3.9 and 3.13, ruff, build, `twine check`, CLI smoke test in CI.
- [ ] Publish 0.1.0 to PyPI (Trusted Publishing; see `.github/workflows/release.yml` for the one-time setup).
- [ ] Run the Action on a real repository and link a live comment from the README.

## 3. Evaluation (next PR)

- [ ] Re-run the repeat-rate measurement on AIDev review comments.
- [ ] Scan benchmark: a flag counts as a catch only if a later commit in the same PR changed the flagged line;
      report catches and false alarms per 100 PRs, as Jinx does.
- [ ] Kill rule, fixed in advance: a built-in check is removed (or kept off by default) below 5% coverage or
      above 3 false alarms per 100 PRs.
- [ ] Audit benchmark: share of AGENTS.md rules that are enforceable but unenforced across public repos.

## 4. Later

- [ ] `trellis mine`: map repeated review comments to existing lint rules, with evidence links.
- [ ] ast-grep emission for rules that need syntax.
- [ ] Verification evidence (screenshots, test output) for agent PRs.
- [ ] Site and demo, as for Jinx.

## Naming

Distribution `rd0-trellis`, import `rd0_trellis`, CLI `trellis` (and `rd0-trellis`, so `uvx rd0-trellis` works).
`rd0-deja` was the alternative; both were free on PyPI when checked.
