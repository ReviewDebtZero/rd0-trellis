"""Run the checks over a diff: `scan` lists findings on added lines; `ratchet` compares rule counts
between the old and new side of the diff, so moved code is not counted as new."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import paths as P
from .config import Config
from .diff import FileDiff
from .rules import CustomLineRule, Finding, line_rules, scope_findings


def _eligible(f: FileDiff, config: Config) -> bool:
    return not P.is_skipped(f.path, config.ignore)


def scan(files: list, pr_text: str = "", config: Config | None = None) -> list:
    """Findings on lines and files the PR adds. Every rule is a warning unless configured otherwise."""
    config = config or Config()
    out: list = []
    for rule in line_rules(config):
        for f in files:
            if f.status == "deleted" or not _eligible(f, config) or not rule.applies(f.path):
                continue
            for no, snippet, msg, fix in rule.hits(f.path, f.added):
                ev = list(rule.rule.evidence) if isinstance(rule, CustomLineRule) else []
                out.append(Finding(rule.id, rule.level, f.path, no, msg, fix, snippet[:200], ev))
    out += scope_findings(files, pr_text, config)
    out.sort(key=lambda x: (x.path, x.line or 0, x.rule))
    return out


@dataclass
class RuleCount:
    rule: str
    level: str
    added: int = 0
    removed: int = 0
    remaining: int | None = None
    files: dict = field(default_factory=dict)

    @property
    def net(self) -> int:
        return self.added - self.removed

    @property
    def failed(self) -> bool:
        return self.level == "error" and self.net > 0

    def to_dict(self) -> dict:
        d = {"rule": self.rule, "level": self.level, "added": self.added, "removed": self.removed, "net": self.net}
        if self.remaining is not None:
            d["remaining"] = self.remaining
        d["failed"] = self.failed
        return d


def ratchet(files: list, config: Config | None = None, root: str | None = None) -> list:
    """Per-rule counts: added and removed occurrences across the whole diff, and (with `root`) how many
    are left in the tree. A rule set to `error` fails only when its count goes up."""
    config = config or Config()
    rules = line_rules(config)
    counts = []
    for rule in rules:
        rc = RuleCount(rule.id, rule.level)
        for f in files:
            if not _eligible(f, config):
                continue
            if f.status != "deleted" and rule.applies(f.path):
                n = len(rule.hits(f.path, f.added))
                rc.added += n
                if n:
                    rc.files[f.path] = rc.files.get(f.path, 0) + n
            old = f.old_path or f.path
            if f.removed and rule.applies(old):
                rc.removed += len(rule.hits(old, f.removed))
        counts.append(rc)
    if root:
        custom = [r for r in rules if isinstance(r, CustomLineRule)]
        totals = count_tree(root, custom, config)
        for rc in counts:
            if rc.rule in totals:
                rc.remaining = totals[rc.rule]
    return counts


def count_tree(root: str, rules: list, config: Config) -> dict:
    totals = {r.id: 0 for r in rules}
    if not rules:
        return totals
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "vendor", "dist",
                                                                                     "build", "__pycache__")]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if P.is_skipped(rel, config.ignore):
                continue
            todo = [r for r in rules if r.applies(rel)]
            if not todo:
                continue
            try:
                with open(full, encoding="utf-8") as fh:
                    lines = list(enumerate(fh.read().splitlines(), 1))
            except (OSError, UnicodeDecodeError):
                continue
            for r in todo:
                totals[r.id] += len(r.hits(rel, lines))
    return totals
