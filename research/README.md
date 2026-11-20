# Evaluation on AIDev

Data: [AIDev](https://huggingface.co/datasets/hao-li/AIDev) (`pull_request`, `pr_commits`, `pr_commit_details`,
`repository` parquet files, about 13.5 GB). Download them into one directory first.

| Script | Output | What it measures |
|---|---|---|
| `experiments/eval_v1/eval_scan.py` | `results/scan_v1.json` | `trellis scan` on every commit of 12,000 sampled agent PRs with 2 or more commits (seed 0). A line flag is *undone* when another commit in the PR removes the same line from the same file. A file flag is *undone* when the PR's other commits revert every line the file gained or lost. |
| `experiments/eval_v1/eval_audit.py` | `results/audit_v1.json` | `trellis audit` on randomly sampled non-fork AIDev repositories, read from the GitHub API. |

```bash
pip install -e "packages/rd0-trellis" pyarrow
python research/experiments/eval_v1/eval_scan.py ~/aidev research/results/scan_v1.json --sample 12000
GITHUB_TOKEN=... python research/experiments/eval_v1/eval_audit.py ~/aidev research/results/audit_v1.json --sample 300
```

`eval_scan.py` peaks at about 12 GB of RAM on 12,000 PRs and takes about 12 minutes. 30,000 PRs needs more than 30 GB.

## Definitions

- **Baseline:** the share of all added code lines that another commit removes (`base_rate_line_undone`), and the
  share of all changed files that the PR's other commits fully revert (`base_rate_file_reverted`).
- **False alarms per 100 PRs:** merged PRs where none of a check's flags were undone, per 100 sampled PRs
  (`prs_all_flags_survived_merged`). This is an upper bound: some surviving flags were real problems that the
  team accepted.
- **Kill rule, fixed before the run:** a built-in check stays on by default only if at least 5% of its flags are
  undone and it has at most 3 false alarms per 100 PRs.

## Threats to validity

- AIDev has no commit timestamps, so "another commit" stands in for "a later commit".
- Being undone is a proxy for being corrected. A line can also be rewritten during ordinary iteration, which is
  why each rate is compared with the baseline.
- PRs with one commit (40% of AIDev) cannot show a correction and are excluded.
