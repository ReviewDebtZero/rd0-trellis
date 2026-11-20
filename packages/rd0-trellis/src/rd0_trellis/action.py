"""GitHub Action entry point: scan the PR's diff, ratchet its rules, and keep one comment up to date.

Reads only the GitHub API (no checkout, so `pull_request_target` is safe). `trellis.toml` is read from
the base branch, so a PR cannot change its own rules."""

from __future__ import annotations

import json
import os
import sys

from .config import CONFIG_FILES, Config
from .diff import from_github_files
from .engine import ratchet, scan
from .github import GitHub
from .report import MARKER, markdown


def load_config(gh: GitHub, ref: str, path: str = "") -> Config:
    for p in [path] if path else CONFIG_FILES:
        text = gh.read(p, ref)
        if text is not None:
            return Config.from_toml(text, source=p)
    return Config()


def _ours(c: dict, me: str) -> bool:
    """A marker comment by a bot, or by the token's own user (a personal access token). Anyone else can
    paste the marker into their own comment, so it alone is not enough."""
    if MARKER not in (c.get("body") or ""):
        return False
    user = c.get("user") or {}
    return user.get("type") == "Bot" or (bool(me) and user.get("login") == me)


def run(event: dict, gh: GitHub, config_path: str = "", comment: bool = True):
    """Returns (comment body or None, failed)."""
    pr = event["pull_request"]
    number = pr["number"]
    base = (pr.get("base") or {}).get("sha") or (pr.get("base") or {}).get("ref")
    config = load_config(gh, base, config_path)
    files = from_github_files(gh.pages(f"/pulls/{number}/files", 3000))
    text = f"{pr.get('title') or ''}\n{pr.get('body') or ''}"
    findings = scan(files, text, config)
    counts = ratchet(files, config)
    # Scope findings are per file, not counted, so an `error` scope finding fails on its own.
    failed = any(rc.failed for rc in counts) or any(f.rule == "scope" and f.level == "error" for f in findings)
    marked = [c for c in gh.pages(f"/issues/{number}/comments", 300) if MARKER in (c.get("body") or "")]
    me = gh.whoami() if any((c.get("user") or {}).get("type") != "Bot" for c in marked) else ""
    old = [c for c in marked if _ours(c, me)]
    if not findings and not failed and not old:
        return None, False
    body = markdown(findings, counts)
    if comment:
        if old:
            if old[0].get("body") != body:
                gh.call("PATCH", f"/issues/comments/{old[0]['id']}", {"body": body})
        else:
            gh.call("POST", f"/issues/{number}/comments", {"body": body})
    return body, failed


def main() -> int:
    with open(os.environ["GITHUB_EVENT_PATH"]) as fh:
        event = json.load(fh)
    if "pull_request" not in event:
        print("rd0_trellis: not a pull_request event, skipping")
        return 0
    gh = GitHub(os.environ["INPUT_GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"])
    body, failed = run(
        event,
        gh,
        os.environ.get("INPUT_CONFIG", ""),
        os.environ.get("INPUT_COMMENT", "true").lower() == "true",
    )
    print(body or "rd0_trellis: nothing to report")
    fail_on = os.environ.get("INPUT_FAIL_ON", "error").lower()
    if failed and fail_on == "error":
        print("rd0_trellis: a rule set to `error` got worse in this PR", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
