"""Minimal GitHub REST client (stdlib only). A token is optional for public repos but raises the rate limit."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
PR_REF = re.compile(
    r"^(?:https?://github\.com/)?(?P<repo>[\w.-]+/[\w.-]+?)(?:/pull/|/pulls/|#)(?P<num>\d+)(?:[/?#].*)?$"
)
REPO_REF = re.compile(r"^(?:https?://github\.com/)?(?P<repo>[\w.-]+/[\w.-]+?)(?:\.git)?/?$")


def parse_pr_ref(ref: str):
    m = PR_REF.match(ref.strip())
    return (m.group("repo"), int(m.group("num"))) if m else None


def parse_repo_ref(ref: str):
    m = REPO_REF.match(ref.strip())
    return m.group("repo") if m else None


class GitHub:
    def __init__(self, token: str | None = None, repo: str = ""):
        self.token = token if token is not None else (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
        self.repo = repo

    def _req(self, method: str, url: str, body=None, accept="application/vnd.github+json"):
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", accept)
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "rd0-trellis")
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()

    def call(self, method: str, path: str, body: dict | None = None):
        raw = self._req(method, f"{API}/repos/{self.repo}{path}", body)
        return json.loads(raw or b"null")

    def whoami(self) -> str:
        """Login of the token's user, or "" (the Actions GITHUB_TOKEN cannot read /user)."""
        try:
            return (json.loads(self._req("GET", f"{API}/user", None) or b"null") or {}).get("login") or ""
        except Exception:
            return ""

    def pages(self, path: str, limit: int):
        out, page = [], 1
        while len(out) < limit:
            sep = "&" if "?" in path else "?"
            batch = self.call("GET", f"{path}{sep}per_page=100&page={page}")
            if not batch:
                break
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return out[:limit]

    def pull(self, number: int):
        return self.call("GET", f"/pulls/{number}"), self.pages(f"/pulls/{number}/files", 3000)

    def tree(self, ref: str = "HEAD") -> list:
        d = self.call("GET", f"/git/trees/{ref}?recursive=1")
        return [t["path"] for t in d.get("tree", []) if t.get("type") == "blob"]

    def read(self, path: str, ref: str | None = None) -> str | None:
        q = f"?ref={ref}" if ref else ""
        try:
            d = self.call("GET", f"/contents/{path}{q}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        if not isinstance(d, dict) or d.get("encoding") != "base64":
            return None
        return base64.b64decode(d["content"]).decode("utf-8", "replace")
