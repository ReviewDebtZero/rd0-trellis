"""Unified diff parsing: which files changed, and which lines were added or removed."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FileDiff:
    path: str
    status: str = "modified"  # added | deleted | modified | renamed
    old_path: str = ""
    added: list = field(default_factory=list)  # (new line number, text)
    removed: list = field(default_factory=list)  # (old line number, text)

    @property
    def is_new(self) -> bool:
        return self.status == "added"


def _strip(p: str) -> str:
    p = p.strip().split("\t", 1)[0]
    if p.startswith('"') and p.endswith('"'):
        p = p[1:-1]
    return p[2:] if p[:2] in ("a/", "b/") else p


def parse_diff(text: str) -> list[FileDiff]:
    """Parse `git diff` output, or a concatenation of GitHub API `patch` fields with file headers."""
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    old_no = new_no = 0
    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            parts = raw[len("diff --git ") :].split(" b/", 1)
            path = parts[1] if len(parts) == 2 else _strip(parts[0])
            cur = FileDiff(path=path.strip(), old_path=_strip(parts[0]))
            files.append(cur)
            continue
        if cur is None:
            if raw.startswith("--- "):
                cur = FileDiff(path="", old_path=_strip(raw[4:]))
                files.append(cur)
            else:
                continue
        if raw.startswith("new file mode"):
            cur.status = "added"
        elif raw.startswith("deleted file mode"):
            cur.status = "deleted"
        elif raw.startswith("rename to "):
            cur.status, cur.path = "renamed", raw[len("rename to ") :].strip()
        elif raw.startswith("--- ") and not cur.added and not cur.removed:
            if raw[4:].strip() == "/dev/null":
                cur.status = "added"
        elif raw.startswith("+++ ") and not cur.added and not cur.removed:
            p = raw[4:].strip()
            if p == "/dev/null":
                cur.status = "deleted"
            else:
                cur.path = _strip(p)
        elif raw.startswith("@@"):
            m = HUNK.match(raw)
            if m:
                old_no, new_no = int(m.group(1)), int(m.group(3))
        elif raw.startswith("+"):
            cur.added.append((new_no, raw[1:]))
            new_no += 1
        elif raw.startswith("-"):
            cur.removed.append((old_no, raw[1:]))
            old_no += 1
        elif raw.startswith(" ") or raw == "":
            old_no += 1
            new_no += 1
    for f in files:
        if not f.path:
            f.path = f.old_path
    return [f for f in files if f.path]


def from_github_files(files: list[dict]) -> list[FileDiff]:
    """Build FileDiffs from the GitHub `GET /pulls/{n}/files` response."""
    out = []
    for f in files:
        status = {"removed": "deleted"}.get(f.get("status", ""), f.get("status") or "modified")
        if status not in ("added", "deleted", "renamed"):
            status = "modified"
        fd = parse_diff(f"diff --git a/{f['filename']} b/{f['filename']}\n{f.get('patch') or ''}\n")
        d = fd[0] if fd else FileDiff(path=f["filename"])
        d.path, d.status, d.old_path = f["filename"], status, f.get("previous_filename") or f["filename"]
        out.append(d)
    return out
