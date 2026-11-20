# rd0-trellis

**Trellis stops your team from reviewing the same mistake twice.** Part of
[rd0](https://github.com/harshuljain13/rd0-jinx) — review debt, to zero.

Coding agents read AGENTS.md and still make the mistakes it forbids. Trellis turns those rules into checks:

- `trellis audit [path | owner/repo]` reads AGENTS.md, CLAUDE.md, `.cursor/rules` and Copilot instructions,
  reports which rules nothing enforces, and writes ESLint, Ruff, import-linter or `trellis.toml` config for them.
- `trellis scan [PR-url | file.diff]` flags agent slop with no config: scope creep (lockfiles, CI config,
  `.gitignore`, summary docs nobody asked for, files the PR doesn't mention), comments that excuse a
  workaround, lint/type suppressions with no reason, and commented-out code.
- `trellis check` ratchets: it fails only when a rule set to `error` has more hits after the change than
  before, and reports the debt that is left.

Pure Python, no LLM, no API key. Python 3.9+.

```console
$ pip install rd0-trellis
$ trellis audit .
AGENTS.md: 13 rules. 1 enforced by a check, 9 could be (10 of 13 are checkable), 3 are judgment calls.
$ trellis scan https://github.com/OWNER/REPO/pull/123
$ trellis check --base origin/main
```

```python
import rd0_trellis

report = rd0_trellis.audit(".")
print(report.headline())

files = rd0_trellis.parse_diff(open("pr.diff").read())
for f in rd0_trellis.scan(files, pr_text="Fix the login timeout"):
    print(f.where, f.rule, f.message)
```

The GitHub Action, `trellis.toml` reference and the full guide are at
https://github.com/harshuljain13/rd0-trellis.
