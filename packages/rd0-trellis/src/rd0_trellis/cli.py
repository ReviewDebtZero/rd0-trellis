from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from . import __version__
from .config import Config
from .diff import from_github_files, parse_diff
from .engine import ratchet, scan
from .github import GitHub, parse_pr_ref
from .report import markdown, text_findings, text_ratchet
from .rules import scope_findings


def _git_diff(base: str | None) -> str:
    args = ["git", "diff", "--no-color", "--no-ext-diff", "-M"]
    args += [f"{base}...HEAD"] if base else ["HEAD"]
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise SystemExit(f"trellis: could not run {' '.join(args)}: {e}") from e


def load_target(target: str | None, base: str | None, title: str, body: str):
    """(files, PR text, label). TARGET is a PR URL or owner/repo#N, a diff file, `-` for stdin, or
    nothing for the local `git diff`."""
    text = f"{title}\n{body}"
    if target and parse_pr_ref(target):
        repo, number = parse_pr_ref(target)
        gh = GitHub(repo=repo)
        pr, files = gh.pull(number)
        text = f"{pr.get('title') or ''}\n{pr.get('body') or ''}\n{text}"
        return from_github_files(files), text, f"{repo}#{number}: "
    if target == "-":
        return parse_diff(sys.stdin.read()), text, ""
    if target:
        with open(target, encoding="utf-8") as fh:
            return parse_diff(fh.read()), text, f"{target}: "
    return parse_diff(_git_diff(base)), text, ""


def _config(a) -> Config:
    try:
        return Config.load(a.config)
    except (ValueError, FileNotFoundError) as e:
        raise SystemExit(f"trellis: config error: {e}") from e


def cmd_scan(a) -> int:
    files, text, label = load_target(a.target, a.base, a.title, a.body)
    config = _config(a)
    findings = scan(files, text, config)
    if a.format == "json":
        print(json.dumps({"files": len(files), "findings": [f.to_dict() for f in findings]}, indent=2))
    elif a.format == "markdown":
        print(markdown(findings))
    else:
        print(text_findings(findings, label))
    if a.strict and findings:
        return 1
    return 1 if any(f.level == "error" for f in findings) else 0


def cmd_check(a) -> int:
    files, text, label = load_target(a.target, a.base, a.title, a.body)
    config = _config(a)
    root = a.root or (None if a.target and parse_pr_ref(a.target) else ".")
    counts = ratchet(files, config, root=root if root and os.path.isdir(root) else None)
    scope = [f for f in scope_findings(files, text, config) if f.level == "error"]
    if a.json:
        print(json.dumps({"rules": [rc.to_dict() for rc in counts], "scope": [f.to_dict() for f in scope]}, indent=2))
    else:
        print(text_ratchet(counts))
        if scope:
            print(text_findings(scope, label))
    return 1 if scope or any(rc.failed for rc in counts) else 0


def cmd_audit(a) -> int:
    from .audit import audit

    try:
        report = audit(a.target)
    except FileNotFoundError as e:
        raise SystemExit(f"trellis: {e}") from e
    if a.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.text())
    if a.write:
        os.makedirs(a.write, exist_ok=True)
        for name, body in report.emitted.items():
            path = os.path.join(a.write, name.replace("/", "_") + ".trellis")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            print(f"wrote {path}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="trellis", description="Stop reviewing the same mistake twice: turn agent rules into checks."
    )
    p.add_argument("--version", action="version", version=f"rd0-trellis {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def target_args(c):
        c.add_argument("target", nargs="?", help="PR URL or owner/repo#N, a diff file, or - for stdin "
                                                 "(default: local `git diff HEAD`)")
        c.add_argument("--base", help="with no target, diff BASE...HEAD instead of the working tree")
        c.add_argument("--config", help="path to trellis.toml (default: ./trellis.toml if present)")
        c.add_argument("--title", default="", help="PR title, for the scope check on local diffs")
        c.add_argument("--body", default="", help="PR description, for the scope check on local diffs")

    s = sub.add_parser("scan", help="flag agent slop in a PR: scope creep, workaround comments, bare suppressions, "
                                    "commented-out code, custom rules")
    target_args(s)
    s.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    s.add_argument("--json", dest="format", action="store_const", const="json")
    s.add_argument("--strict", action="store_true", help="exit 1 on any finding, not only error-level ones")
    s.set_defaults(fn=cmd_scan)

    c = sub.add_parser("check", help="ratchet: fail only if a rule set to `error` has more hits after the change")
    target_args(c)
    c.add_argument("--root", help="count what is left in this tree (default: . for local diffs)")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)

    au = sub.add_parser("audit", help="which rules in AGENTS.md / CLAUDE.md / .cursor/rules are enforced, and "
                                      "config for the rest")
    au.add_argument("target", nargs="?", default=".", help="repo directory or owner/repo (default: .)")
    au.add_argument("--json", action="store_true")
    au.add_argument("--write", metavar="DIR", help="also write the generated config snippets into DIR")
    au.set_defaults(fn=cmd_audit)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
