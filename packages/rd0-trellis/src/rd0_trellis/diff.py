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
    """Parse `git diff` output, or a concatenation of GitHub API `patch` fields with file headers.

    Hunk line counts decide what is content, so a removed `-- comment` or an added `++ i;` is never read
    as a file header."""
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    old_no = new_no = old_left = new_left = 0
    seen_hunk = False
    # split("\n"), not splitlines(): source lines may contain U+2028, \x0c and other separators.
    for raw in (ln[:-1] if ln.endswith("\r") else ln for ln in text.split("\n")):
        if cur is not None and (old_left > 0 or new_left > 0):
            tag = raw[:1]
            if tag == "+":
                cur.added.append((new_no, raw[1:]))
                new_no += 1
                new_left -= 1
                continue
            if tag == "-":
                cur.removed.append((old_no, raw[1:]))
                old_no += 1
                old_left -= 1
                continue
            if tag == " " or raw == "":
                old_no += 1
                new_no += 1
                old_left -= 1
                new_left -= 1
                continue
            if tag == "\\":
                continue
            old_left = new_left = 0
        if raw.startswith("diff --git "):
            parts = raw[len("diff --git ") :].split(" b/", 1)
            path = parts[1] if len(parts) == 2 else _strip(parts[0])
            cur = FileDiff(path=path.strip(), old_path=_strip(parts[0]))
            files.append(cur)
            seen_hunk = False
            continue
        if raw.startswith("--- "):
            if cur is None or seen_hunk:
                cur = FileDiff(path="", old_path=_strip(raw[4:]))
                files.append(cur)
                seen_hunk = False
            if raw[4:].strip() == "/dev/null":
                cur.status = "added"
            continue
        if cur is None:
            continue
        if raw.startswith("new file mode"):
            cur.status = "added"
        elif raw.startswith("deleted file mode"):
            cur.status = "deleted"
        elif raw.startswith("rename to "):
            cur.status, cur.path = "renamed", raw[len("rename to ") :].strip()
        elif raw.startswith("+++ ") and not seen_hunk:
            p = raw[4:].strip()
            if p == "/dev/null":
                cur.status = "deleted"
            else:
                cur.path = _strip(p)
        elif raw.startswith("@@"):
            m = HUNK.match(raw)
            if m:
                old_no, new_no = int(m.group(1)), int(m.group(3))
                old_left = int(m.group(2)) if m.group(2) is not None else 1
                new_left = int(m.group(4)) if m.group(4) is not None else 1
                seen_hunk = True
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
