# Trellis user guide

Trellis has three commands. `audit` tells you which of your agent rules nothing enforces and writes the
config for them. `scan` flags agent slop in a PR. `check` is the ratchet that fails a PR only when a rule
you set to `error` got worse. All three are pure Python with no LLM and no API key.

## As a GitHub Action

Add the workflow from the [README](../README.md#add-it-to-your-repo). Inputs:

| Input | Default | Meaning |
|---|---|---|
| `github-token` | `${{ github.token }}` | Reads the PR and posts the comment. Needs `pull-requests: write` and `issues: write`. |
| `config` | `""` | Path to `trellis.toml` in the base branch. Empty: `trellis.toml`, `.trellis.toml`, then `.github/trellis.toml`. |
| `comment` | `"true"` | `"false"` prints the report to the job log only. |
| `fail-on` | `"error"` | `"error"` fails the job when an `error` rule got worse; `"never"` only comments. |

The Action posts one comment (marked `<!-- rd0_trellis:v1 -->`), edits it on every push, and posts nothing on
a clean PR. If an earlier run commented and the PR is now clean, it edits the comment to say so. It reads the
diff from the API and `trellis.toml` from the base commit, never the PR's code.

## Command line

```console
pip install rd0-trellis          # or: uvx rd0-trellis <command>
```

### `trellis audit [path | owner/repo] [--json] [--write DIR]`

Finds `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursorrules`, `.cursor/rules/**`, `.github/copilot-instructions.md`,
`.github/instructions/**`, `.windsurfrules`, `.clinerules` and `CONVENTIONS.md` (including nested ones), splits them
into rules, and puts each rule in one of three groups:

- **enforced**: your ESLint, Ruff, import-linter or Trellis config already checks it;
- **enforceable**: a known check exists, and Trellis prints the config for it;
- **judgment**: keep it as prose (or rethink it).

`owner/repo` audits a GitHub repository through the API (set `GITHUB_TOKEN` for private repos or rate limits).
`--write DIR` also saves the generated snippets. The snippets are fragments to merge, not whole files: ESLint
rules from plugins (`@typescript-eslint`, `import`) need those plugins installed.

### `trellis scan [target] [--config F] [--title T] [--body B] [--format text|json|markdown] [--strict]`

`target` is a PR (`https://github.com/o/r/pull/1` or `o/r#1`), a diff file, `-` for stdin, or nothing for your
local `git diff HEAD` (`--base main` diffs `main...HEAD`). For local diffs, pass `--title`/`--body` so the scope
check knows what the change is meant to do.

Exit code: 1 if any finding is at `error` level (or any finding at all with `--strict`), else 0.

Built-in checks (all `warn` by default):

| Rule | Flags |
|---|---|
| `scope` | Lockfile changed without its manifest or a mention of dependencies; `.gitignore` or CI config changed with no reason given; new `*SUMMARY*`/`*NOTES*`/`*REPORT*`-style docs; files outside every path the PR description names; any file under `[trellis.scope] protect`. |
| `workaround-comment` | Added comments such as "workaround", "hack", "for now", "to avoid the error", "until X is fixed", "FIXME". |
| `bare-suppression` | `eslint-disable`, `@ts-ignore`, `@ts-nocheck`, `@ts-expect-error`, `# noqa`, `# type: ignore`, `# pyright: ignore`, `//nolint`, `rubocop:disable` with no rule code or no reason. A comment on the line above counts as a reason. |
| `commented-out-code` | Two or more added comment lines that parse as code, or one that ends in `;` or `{`. |

Lockfiles, generated files (`*.min.js`, `*.snap`, `*_pb2.py`, ...) and vendored directories (`vendor/`,
`node_modules/`, `dist/`, ...) are skipped.

### `trellis check [target] [--config F] [--root DIR] [--json]`

Same targets as `scan`. For every rule it counts hits on removed and added lines; the net change is the
ratchet. A rule at `error` fails when the net is positive, so moving code is not a violation and old debt
never blocks a PR. With a local diff it also counts what is left in the tree (`--root` to pick another
directory). Exit code 1 when any rule failed.

## `trellis.toml`

```toml
[trellis]
ignore = ["docs/**", "**/*.generated.ts"]   # never scanned

[trellis.rules]                              # built-in levels: "off" | "warn" | "error"
scope = "warn"
workaround-comment = "warn"
bare-suppression = "error"
commented-out-code = "warn"

[trellis.scope]
allow = ["CHANGELOG.md"]                     # never flagged by the scope check
protect = ["src/generated/**", "migrations/**"]  # always flagged

[[rule]]
id = "no-direct-fetch"                       # unique, shown in the report
pattern = '\bfetch\('                        # Python regex, matched against each added line
paths = ["src/**/*.ts"]                      # optional globs (`**` spans directories)
exclude = ["src/lib/http.ts"]
message = "Call the API through src/lib/http, not fetch()."
fix = "import { http } from 'src/lib/http' and call http.get/post."
level = "error"
evidence = ["https://github.com/you/app/pull/90#discussion_r7"]   # the review comments it came from
```

The CLI reads `--config`, else `trellis.toml`, `.trellis.toml` or `.github/trellis.toml` in the current
directory. Invalid regexes, unknown levels and duplicate ids are errors.

## Python API

```python
import rd0_trellis
from rd0_trellis import Config, parse_diff, ratchet, scan

report = rd0_trellis.audit("path/to/repo")          # or "owner/repo"
print(report.headline())
print(report.emitted["trellis.toml"])

files = parse_diff(open("pr.diff").read())
config = Config.load("trellis.toml")
for f in scan(files, pr_text="Fix the login timeout", config=config):
    print(f.where, f.level, f.rule, f.message, f.fix)
for rc in ratchet(files, config, root="."):
    print(rc.rule, rc.net, rc.remaining, rc.failed)
```

## Where Trellis sits in the market

| Tool | What it does | How Trellis differs |
|---|---|---|
| ESLint, Ruff, import-linter, dependency-cruiser, Semgrep, ast-grep | Run the rules you write. | Trellis tells you which rules your agent instructions need and writes them in those tools' formats. |
| Betterer, reviewdog | Ratchet or report only new lint results. | Trellis ratchets its own and custom rules with no baseline file, and adds the agent-specific checks. |
| CodeRabbit learnings, Greptile rules, Cursor Bugbot | LLM reviewers that store corrections as prose. | Deterministic checks: the same diff always gets the same answer, at no cost per PR. |
| pstack `/correct` (Cursor) | Turns a correction into a structural fix inside the editor. | Trellis is the CI half: it makes sure the rule holds on every PR, from any agent. |
