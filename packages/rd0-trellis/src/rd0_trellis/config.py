"""`trellis.toml`: rule levels, ignored paths, scope settings and custom ratchet rules."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

LEVELS = ("off", "warn", "error")
CONFIG_FILES = ("trellis.toml", ".trellis.toml", ".github/trellis.toml")


@dataclass
class CustomRule:
    id: str
    pattern: str
    message: str = ""
    fix: str = ""
    paths: list = field(default_factory=list)
    exclude: list = field(default_factory=list)
    level: str = "warn"
    evidence: list = field(default_factory=list)

    def __post_init__(self):
        if self.level not in LEVELS:
            raise ValueError(f"rule {self.id}: level must be one of {LEVELS}, got {self.level!r}")
        try:
            self.regex = re.compile(self.pattern)
        except re.error as e:
            raise ValueError(f"rule {self.id}: bad pattern {self.pattern!r}: {e}") from e


@dataclass
class Config:
    levels: dict = field(default_factory=dict)
    ignore: list = field(default_factory=list)
    scope_allow: list = field(default_factory=list)
    scope_protect: list = field(default_factory=list)
    rules: list = field(default_factory=list)
    source: str = ""

    def level(self, rule_id: str, default: str) -> str:
        return self.levels.get(rule_id, default)

    @classmethod
    def from_toml(cls, text: str, source: str = "") -> Config:
        d = tomllib.loads(text)
        top = d.get("trellis", {})
        levels = dict(top.get("rules", {}))
        for k, v in levels.items():
            if v not in LEVELS:
                raise ValueError(f"[trellis.rules] {k}: level must be one of {LEVELS}, got {v!r}")
        scope = top.get("scope", {})
        rules = []
        seen = set()
        for r in d.get("rule", []):
            if "id" not in r or "pattern" not in r:
                raise ValueError("every [[rule]] needs an id and a pattern")
            if r["id"] in seen:
                raise ValueError(f"duplicate rule id {r['id']!r}")
            seen.add(r["id"])
            known = {k: r[k] for k in ("id", "pattern", "message", "fix", "paths", "exclude", "level", "evidence") if k in r}
            rules.append(CustomRule(**known))
        return cls(
            levels=levels,
            ignore=list(top.get("ignore", [])),
            scope_allow=list(scope.get("allow", [])),
            scope_protect=list(scope.get("protect", [])),
            rules=rules,
            source=source,
        )

    @classmethod
    def load(cls, path: str | None = None, root: str = ".") -> Config:
        import os

        candidates = [path] if path else [os.path.join(root, c) for c in CONFIG_FILES]
        for c in candidates:
            if c and os.path.exists(c):
                with open(c, encoding="utf-8") as fh:
                    return cls.from_toml(fh.read(), source=c)
        if path:
            raise FileNotFoundError(path)
        return cls()
