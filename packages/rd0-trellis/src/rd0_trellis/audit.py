"""`trellis audit`: read the agent instruction files (AGENTS.md, CLAUDE.md, Cursor and Copilot rules),
find each rule, and say whether a check already enforces it, a check could enforce it, or it is a
judgment call that has to stay as prose. For the checkable ones it writes native config: ESLint, Ruff,
import-linter or `trellis.toml`."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field

from . import paths as P
from .config import CONFIG_FILES

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

INSTRUCTION_GLOBS = [
    "AGENTS.md",
    "**/AGENTS.md",
    "AGENT.md",
    "CLAUDE.md",
    "**/CLAUDE.md",
    ".claude/CLAUDE.md",
    "GEMINI.md",
    ".cursorrules",
    ".cursor/rules/**/*.md",
    ".cursor/rules/**/*.mdc",
    ".github/copilot-instructions.md",
    ".github/instructions/**/*.md",
    ".windsurfrules",
    ".clinerules",
    ".clinerules/**/*.md",
    "CONVENTIONS.md",
]
ESLINT_FILES = re.compile(r"(^|/)(eslint\.config\.[cm]?[jt]s|\.eslintrc(\.(js|cjs|json|ya?ml))?|package\.json)$")
RUFF_FILES = re.compile(r"(^|/)(ruff\.toml|\.ruff\.toml|pyproject\.toml)$")
IMPORTLINTER_FILES = re.compile(r"(^|/)(\.importlinter|setup\.cfg|pyproject\.toml)$")
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "__pycache__", ".venv", "venv", "third_party"}
MAX_DEPTH = 4

NEG = r"\b(?:never|don'?t|do not|avoid|no|must not|mustn'?t|should ?not|shouldn'?t|without|ban|forbid|disallow|stop)\b"
# Text between a negation and the thing it negates: stays inside one clause.
CLAUSE = r"[^.;:!?\u2013\u2014]{0,30}"
PY_HINT = re.compile(r"\bpython\b|\.py\b|\bdef \w|\b(?:dict|list|Optional)\[|\b(?:mypy|pyright|pytest|noqa)\b|\b[EFW]\d{3}\b")
DIRECTIVE = re.compile(
    r"\b(?:never|don'?t|do not|avoid|must not|mustn'?t|shouldn'?t|should not|always|must|prefer|only use|"
    r"instead of|rather than|forbidden|not allowed|disallow|banned|make sure|ensure|use)\b|^no\s",
    re.IGNORECASE,
)
PROCESS = re.compile(
    r"\b(?:run (?:the )?(?:tests?|linters?|build|checks?|formatter)|commit messages?|branch(?:es)? names?|"
    r"pr (?:title|description)s?|pull request (?:title|description)s?|before (?:you )?(?:commit|push)|"
    r"ask (?:me|the user|a human)|changelog|conventional commits?|open (?:a|the) pr)\b",
    re.IGNORECASE,
)


@dataclass
class Target:
    key: str
    tool: str  # eslint | ruff | import-linter | trellis
    rule: str
    lang: str  # js | py | any
    pattern: re.Pattern
    title: str


def _t(key, tool, rule, lang, pattern, title):
    return Target(key, tool, rule, lang, re.compile(pattern, re.IGNORECASE), title)


CATALOG = [
    # trellis built-ins: things no linter checks
    _t("trellis:commented-out-code", "trellis", "commented-out-code", "any",
       r"commented[- ]out code", "no commented-out code"),
    _t("trellis:bare-suppression", "trellis", "bare-suppression", "any",
       NEG + r".{0,40}(?:disabl|suppress|silenc|ignor)\w*.{0,30}(?:lint|eslint|rules?|warnings?|type errors?|checks?|"
       r"mypy|pyright|typescript)|" + NEG + r".{0,30}(?:noqa|eslint-disable|type: ?ignore)",
       "no unexplained lint or type suppressions"),
    _t("trellis:workaround-comment", "trellis", "workaround-comment", "any",
       r"(?:workarounds?|hacks?|band-?aids?).{0,60}(?:root cause|properly|comment)|fix the (?:root )?cause|"
       + NEG + r".{0,30}(?:hacks|workarounds|quick fixes)",
       "no workarounds explained away in comments"),
    _t("trellis:scope-lockfile", "trellis", "scope", "any",
       NEG + r".{0,50}(?:lock ?files?|package-lock|yarn\.lock|pnpm-lock|poetry\.lock|uv\.lock|cargo\.lock)",
       "lockfiles change only with dependencies"),
    _t("trellis:scope-ci", "trellis", "scope", "any",
       NEG + r".{0,40}(?:modify|change|edit|touch|update).{0,20}(?:ci|workflows?|pipelines?|\.github)",
       "no CI changes without a reason"),
    _t("trellis:scope-docs", "trellis", "scope", "any",
       NEG + r".{0,40}(?:create|add|write|leave|generate).{0,30}(?:summary|summaries|markdown|\.md|report|notes)\b",
       "no stray summary or notes files"),
    _t("trellis:scope", "trellis", "scope", "any",
       r"keep (?:the )?(?:changes?|diffs?|prs?|edits?) (?:small|minimal|focused|scoped|tight)|unrelated (?:files|changes)|"
       r"only (?:change|modify|touch|edit) (?:the )?(?:files|code|what)|minimal (?:changes|diffs?)|scope creep|"
       r"drive-by",
       "keep PRs in scope"),
    # ESLint / TypeScript
    _t("eslint:no-console", "eslint", "no-console", "js",
       NEG + r".{0,40}console\.(?:log|debug|info|warn|error)|" + NEG + r".{0,30}console (?:statements|logs?|logging|calls)",
       "no console.log"),
    _t("eslint:@typescript-eslint/no-explicit-any", "eslint", "@typescript-eslint/no-explicit-any", "js",
       NEG + r".{0,40}(?:`any`|\bany\b types?|type `?any`?|as any|: any|explicit any)", "no `any`"),
    _t("eslint:@typescript-eslint/ban-ts-comment", "eslint", "@typescript-eslint/ban-ts-comment", "js",
       NEG + r".{0,40}(?:ts-ignore|ts-nocheck)", "no @ts-ignore"),
    _t("eslint:@typescript-eslint/no-non-null-assertion", "eslint", "@typescript-eslint/no-non-null-assertion",
       "js", NEG + r".{0,40}non-null assertions?", "no non-null assertions"),
    _t("eslint:no-var", "eslint", "no-var", "js", NEG + r".{0,20}(?:use|using) `?var`?\b", "no var"),
    _t("eslint:prefer-const", "eslint", "prefer-const", "js",
       r"(?:prefer|use) `?const`? (?:over|instead of|rather than|unless)", "prefer const"),
    _t("eslint:eqeqeq", "eslint", "eqeqeq", "js",
       r"(?:use|prefer|always use) `?===|triple equals|strict equality|" + NEG + r".{0,30}(?:`==`|loose equality)", "strict equality"),
    _t("eslint:no-eval", "eslint", "no-eval", "js", NEG + r".{0,30}\beval\b", "no eval"),
    _t("eslint:no-debugger", "eslint", "no-debugger", "js", NEG + r".{0,30}\bdebugger\b", "no debugger"),
    _t("eslint:import/no-default-export", "eslint", "import/no-default-export", "js",
       NEG + r".{0,30}default exports?|(?:prefer|use|always use) named exports", "named exports only"),
    _t("eslint:no-nested-ternary", "eslint", "no-nested-ternary", "js", NEG + r".{0,30}nested ternar", "no nested ternaries"),
    _t("eslint:no-restricted-syntax:enum", "eslint", "no-restricted-syntax", "js",
       NEG + r".{0,30}(?:typescript |ts )?enums?\b", "no TypeScript enums"),
    # Ruff / Python
    _t("ruff:T201", "ruff", "T201", "py", NEG + r".{0,30}`?\bprint\b(?:\(\))?`?(?! ?(?:ing|ed|er|out))", "no print()"),
    _t("ruff:T100", "ruff", "T100", "py", NEG + r".{0,30}(?:breakpoint\(\)|\bpdb\b|\bipdb\b)", "no debugger calls"),
    _t("ruff:E722", "ruff", "E722", "py", r"bare `?except`?|" + NEG + r".{0,30}`except:`", "no bare except"),
    _t("ruff:F403", "ruff", "F403", "py", r"(?:star|wildcard) imports?|import \*", "no star imports"),
    _t("ruff:TID252", "ruff", "TID252", "py",
       NEG + r".{0,30}relative imports|(?:use|prefer|always use) absolute imports", "absolute imports"),
    _t("ruff:PTH", "ruff", "PTH", "py", r"(?:use|prefer) `?pathlib`?|" + NEG + r".{0,30}os\.path", "pathlib over os.path"),
    _t("ruff:G004", "ruff", "G004", "py", r"f-?strings? (?:in|for|with) (?:log|logger|logging)", "no f-strings in logging"),
    _t("ruff:S113", "ruff", "S113", "py", r"timeouts?.{0,40}\brequests?\b|\brequests?\b.{0,40}timeouts?",
       "HTTP requests need a timeout"),
    _t("ruff:B006", "ruff", "B006", "py", r"mutable default", "no mutable default arguments"),
    _t("ruff:DTZ", "ruff", "DTZ", "py", r"timezone[- ]aware|naive datetimes?|utcnow", "timezone-aware datetimes"),
    _t("ruff:S602", "ruff", "S602", "py", r"shell ?= ?true", "no shell=True"),
    _t("ruff:S301", "ruff", "S301", "py", NEG + r".{0,30}\bpickle\b", "no pickle"),
    _t("ruff:ANN", "ruff", "ANN", "py", r"type (?:hints|annotations) (?:on|for|everywhere)|(?:add|always use|use) type (?:hints|annotations)",
       "type annotations"),
    # either language
    _t("any:todo", "any", "todo", "any", NEG + r".{0,30}\b(?:todo|fixme)s?\b", "no TODO comments"),
    _t("any:unused", "any", "unused", "any", r"unused (?:imports?|variables?|vars|code)", "no unused imports or variables"),
]

BOUNDARY = re.compile(
    NEG + r".{0,30}import(?:ing|s)?\s+(?:anything\s+)?(?:from\s+)?`([^`]+)`.{0,40}?\b(?:in|into|inside|within|from)\s+`([^`]+)`",
    re.IGNORECASE,
)
INSTEAD = re.compile(
    r"(?:use|prefer|always use)\s+`([^`]+)`\s*(?:,\s*)?(?:instead of|over|rather than|not)\s+`([^`]+)`|"
    + NEG + r".{0,20}(?:use|call)\s+`([^`]+)`[^.;]{0,40}?(?:;|,|\.|-|—)?\s*(?:use|prefer)\s+`([^`]+)`",
    re.IGNORECASE,
)
BANNED_IMPORT = re.compile(
    NEG + r".{0,30}(?:import(?:ing)?|install(?:ing)?|depend(?:ing)? on)\s+(?:the\s+)?`([^`]+)`|"
    + NEG + r".{0,30}(?:use|using|add|adding)\s+(?:the\s+)?`([^`]+)`\s+(?:as\s+an?\s+)?(?:library|package|module|dependency|lib|crate)",
    re.IGNORECASE,
)
BANNED_NAME = re.compile(NEG + CLAUSE + r"(?:use|call|using|calling|add|write)\s+`([^`]+)`", re.IGNORECASE)
PROTECT = re.compile(
    NEG + r".{0,30}(?:edit|modify|change|touch|commit to|write to|update)\s+(?:files? (?:in|under)\s+)?(?:the\s+)?"
    r"`([^`]*/[^`]*|[^`\s]+\.\w{1,6})`",
    re.IGNORECASE,
)

ESLINT_MAP_PY = {"todo": ("ruff", "FIX002"), "unused": ("ruff", "F401")}
ESLINT_MAP_JS = {"todo": ("eslint", "no-warning-comments"), "unused": ("eslint", "@typescript-eslint/no-unused-vars")}


@dataclass
class AuditItem:
    file: str
    line: int
    text: str
    status: str  # enforced | enforceable | judgment
    tool: str = ""
    rule: str = ""
    title: str = ""
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in ("", None, {}, [])}


@dataclass
class AuditReport:
    target: str
    files: list
    items: list
    langs: list
    emitted: dict = field(default_factory=dict)

    def count(self, status: str) -> int:
        return sum(1 for i in self.items if i.status == status)

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "instruction_files": self.files,
            "rules": len(self.items),
            "enforced": self.count("enforced"),
            "enforceable": self.count("enforceable"),
            "judgment": self.count("judgment"),
            "items": [i.to_dict() for i in self.items],
            "config": self.emitted,
        }

    def headline(self) -> str:
        if not self.files:
            return "No agent instruction files found (AGENTS.md, CLAUDE.md, .cursor/rules, copilot-instructions.md)."
        checkable = self.count("enforced") + self.count("enforceable")
        names = ", ".join(self.files[:3]) + (f" and {len(self.files) - 3} more" if len(self.files) > 3 else "")
        return (
            f"{names}: {len(self.items)} rules. {self.count('enforced')} enforced by a check, "
            f"{self.count('enforceable')} could be ({checkable} of {len(self.items)} are checkable), "
            f"{self.count('judgment')} are judgment calls."
        )

    def text(self) -> str:
        out = [self.headline()]
        for status, label in (("enforceable", "Not enforced, but a check can do it"), ("enforced", "Already enforced"),
                              ("judgment", "Judgment calls (keep as prose)")):
            rows = [i for i in self.items if i.status == status]
            if not rows:
                continue
            out += ["", f"{label} ({len(rows)}):"]
            for i in rows:
                tag = f"  [{i.tool}: {i.rule}]" if i.tool else ""
                out.append(f"  {i.file}:{i.line}  {i.text[:100]}{tag}")
        if self.emitted:
            out += ["", "Config for the enforceable rules (paste into your repo, then run it in CI):"]
            for name, body in self.emitted.items():
                out += ["", f"--- {name} ---", body.rstrip()]
        return "\n".join(out)


# ---- sources -----------------------------------------------------------------------------------------


class LocalSource:
    def __init__(self, root: str):
        self.root = root

    def list(self) -> list:
        out = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            rel = os.path.relpath(dirpath, self.root)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            dirnames[:] = [
                d for d in dirnames if d not in SKIP_DIRS and depth < MAX_DEPTH and (not d.startswith(".") or d in
                                                                                     (".github", ".cursor", ".claude",
                                                                                      ".clinerules"))
            ]
            for n in filenames:
                out.append(os.path.normpath(os.path.join(rel, n)).replace(os.sep, "/"))
        return sorted(out)

    def read(self, path: str) -> str | None:
        try:
            with open(os.path.join(self.root, path), encoding="utf-8") as fh:
                return fh.read()
        except (OSError, UnicodeDecodeError):
            return None


class GitHubSource:
    def __init__(self, repo: str, gh=None):
        from .github import GitHub

        self.gh = gh or GitHub(repo=repo)
        self.gh.repo = repo

    def list(self) -> list:
        return [
            p for p in self.gh.tree("HEAD") if p.count("/") < MAX_DEPTH and not any(s in p.split("/") for s in SKIP_DIRS)
        ]

    def read(self, path: str) -> str | None:
        return self.gh.read(path)


# ---- rule extraction ------------------------------------------------------------------------------------


def _clean(s: str) -> str:
    s = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", s)
    s = re.sub(r"\*\*|__|(?<!\w)_(?!\w)", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return s.strip()


def extract_rules(text: str) -> list:
    """(line number, rule sentence) for each line in an instruction file that reads as a rule."""
    out = []
    fence = False
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    for no, raw in enumerate(lines[start:], start + 1):
        s = raw.strip()
        if s.startswith(("```", "~~~")):
            fence = not fence
            continue
        if fence or not s or s.startswith(("#", "|", ">", "<!--")):
            continue
        bullet = bool(re.match(r"^(?:[-*+]|\d+[.)])\s+", s))
        s = _clean(s)
        if len(s) < 8:
            continue
        if bullet:
            if len(s.split()) >= 3 and len(s) <= 400 and not s.endswith(":"):
                out.append((no, s))
            continue
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z`])", s):
            sent = part.strip()
            if 8 <= len(sent) <= 400 and DIRECTIVE.search(sent):
                out.append((no, sent))
    return out


# ---- enforcement detection -------------------------------------------------------------------------------

RUFF_DEFAULT = ["E4", "E7", "E9", "F"]


@dataclass
class Configs:
    eslint: str = ""
    ruff_select: list = field(default_factory=list)
    ruff_ignore: list = field(default_factory=list)
    ruff_text: str = ""
    has_ruff: bool = False
    importlinter: str = ""
    trellis: str = ""
    trellis_in_ci: bool = False
    trellis_levels: dict = field(default_factory=dict)
    langs: list = field(default_factory=list)

    def ruff_on(self, code: str) -> bool:
        if not self.has_ruff:
            return False
        if any(code.startswith(i) for i in self.ruff_ignore if i):
            return False
        return any(s == "ALL" or code.startswith(s) for s in self.ruff_select)


def _eslint_on(text: str, rule: str) -> bool:
    """True if `rule` is configured at a level other than off/0. A bare mention (e.g. an AST selector) counts."""
    keyed = False
    for m in re.finditer(rf"""["']?{re.escape(rule)}["']?\s*:\s*\[?\s*(["']?)([\w-]+)\1""", text):
        keyed = True
        if m.group(2) not in ("off", "0"):
            return True
    return not keyed and rule in text


def _ruff_from(d: dict, cfg: Configs):
    lint = d.get("lint", {})
    select = None
    for src in (d, lint):
        if "select" in src:
            select = list(src["select"])
        cfg.ruff_select += src.get("extend-select", [])
        cfg.ruff_ignore += src.get("ignore", []) + src.get("extend-ignore", [])
    # Like ruff: an explicit `select` (even empty) replaces the defaults; `extend-select` adds to them.
    cfg.ruff_select += RUFF_DEFAULT if select is None else select


def read_configs(paths: list, read) -> Configs:
    cfg = Configs()
    langs = set()
    for p in paths:
        base = os.path.basename(p)
        if base in ("package.json", "tsconfig.json") or P.ext(p) in (".ts", ".tsx", ".js", ".jsx"):
            langs.add("js")
        if base in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt") or P.ext(p) == ".py":
            langs.add("py")
    cfg.langs = sorted(langs)
    ruff_config_found = False
    for p in paths:
        if ESLINT_FILES.search(p):
            t = read(p) or ""
            if os.path.basename(p) != "package.json" or '"eslintConfig"' in t:
                cfg.eslint += "\n" + t
        if RUFF_FILES.search(p):
            t = read(p) or ""
            try:
                d = tomllib.loads(t)
            except Exception:
                d = {}
            if os.path.basename(p) == "pyproject.toml":
                d = d.get("tool", {}).get("ruff")
                if d is None:
                    d = None
            if d is not None:
                cfg.has_ruff = True
                cfg.ruff_text += "\n" + t
                _ruff_from(d, cfg)
                ruff_config_found = True
            if "importlinter" in t:
                cfg.importlinter += "\n" + t
        elif IMPORTLINTER_FILES.search(p):
            t = read(p) or ""
            if "importlinter" in t:
                cfg.importlinter += "\n" + t
        if os.path.basename(p) in ("trellis.toml", ".trellis.toml"):
            cfg.trellis += "\n" + (read(p) or "")
        if p.startswith(".github/workflows/"):
            t = read(p) or ""
            if "rd0-trellis" in t or "rd0_trellis" in t:
                cfg.trellis_in_ci = True
            if "ruff" in t and not cfg.has_ruff:
                cfg.has_ruff = True
    # Rule levels come from the one config trellis itself loads (first of CONFIG_FILES), not nested ones.
    for name in CONFIG_FILES:
        if name in paths:
            try:
                rules = tomllib.loads(read(name) or "").get("trellis", {}).get("rules", {})
                cfg.trellis_levels = {k: v for k, v in rules.items() if isinstance(v, str)}
            except Exception:
                pass
            break
    if cfg.has_ruff and not ruff_config_found:
        cfg.ruff_select += RUFF_DEFAULT
    return cfg


def _module_lang(name: str, langs: list) -> list:
    if "/" in name or name.startswith("@") or "-" in name:
        return ["js"]
    if "." in name or "_" in name:
        return ["py"] if "py" in langs or not langs else ["py"]
    return langs or ["js", "py"]


def _rx(name: str) -> str:
    name = name.strip().rstrip("()")
    esc = re.escape(name)
    lead = r"\b" if re.match(r"\w", name) else ""
    return lead + esc + (r"\s*\(" if re.match(r"^[\w.$]+$", name) and name[0].islower() else (r"\b" if name[-1:].isalnum() else ""))


class _Emitter:
    def __init__(self, langs):
        self.langs = langs
        self.eslint_rules = {}
        self.eslint_imports = []
        self.eslint_syntax = []
        self.eslint_scoped = []
        self.ruff_select = []
        self.ruff_banned = {}
        self.importlinter = []
        self.trellis_rules = []
        self.trellis_protect = []
        self.trellis_builtins = set()

    def render(self) -> dict:
        out = {}
        rules = dict(self.eslint_rules)
        if self.eslint_imports:
            rules["no-restricted-imports"] = ["error", {"paths": self.eslint_imports}]
        if self.eslint_syntax:
            rules["no-restricted-syntax"] = ["error", *self.eslint_syntax]
        if rules or self.eslint_scoped:
            objs = []
            if rules:
                objs.append({"rules": rules})
            # A later flat-config object replaces a rule's options for its files, so each scoped
            # no-restricted-imports block repeats the repo-wide banned packages.
            # Boundaries on the same directory are merged into one block for the same reason.
            merged = {}
            for o in self.eslint_scoped:
                key = tuple(o["files"])
                if key in merged:
                    merged[key]["rules"]["no-restricted-imports"][1]["patterns"] += (
                        o["rules"]["no-restricted-imports"][1]["patterns"]
                    )
                else:
                    merged[key] = o
            for o in merged.values():
                opts = o["rules"]["no-restricted-imports"][1]
                if self.eslint_imports and "paths" not in opts:
                    opts["paths"] = self.eslint_imports
                objs.append(o)
            body = ",\n".join(json.dumps(o, indent=2) for o in objs)
            out["eslint.config.js"] = (
                "// Add these objects to the array your eslint.config.js exports (written by `trellis audit`).\n"
                + body + ",\n"
            )
        if self.ruff_select or self.ruff_banned:
            lines = ["# pyproject.toml (written by `trellis audit`)", "[tool.ruff.lint]"]
            sel = sorted(set(self.ruff_select) | ({"TID251"} if self.ruff_banned else set()))
            lines.append("extend-select = [" + ", ".join(f'"{c}"' for c in sel) + "]")
            if self.ruff_banned:
                lines += ["", "[tool.ruff.lint.flake8-tidy-imports.banned-api]"]
                for name, msg in self.ruff_banned.items():
                    lines.append(f'"{name}".msg = {json.dumps(msg)}')
            out["pyproject.toml"] = "\n".join(lines) + "\n"
        if self.importlinter:
            out[".importlinter"] = "[importlinter]\nroot_packages = CHANGE_ME\n\n" + "\n".join(self.importlinter)
        if self.trellis_rules or self.trellis_protect or self.trellis_builtins:
            lines = ["# trellis.toml (written by `trellis audit`)", "[trellis.rules]"]
            for b in sorted(self.trellis_builtins | ({"scope"} if self.trellis_protect else set())):
                lines.append(f'{b} = "warn"')
            if self.trellis_protect:
                lines += ["", "[trellis.scope]", "protect = [" + ", ".join(json.dumps(p) for p in self.trellis_protect) + "]"]
            for r in self.trellis_rules:
                lines += ["", "[[rule]]"]
                for k in ("id", "pattern", "message", "fix", "level"):
                    if r.get(k):
                        lines.append(f"{k} = {_toml_str(r[k])}")
            out["trellis.toml"] = "\n".join(lines) + "\n"
        return out


def _toml_str(s: str) -> str:
    return f"'{s}'" if "'" not in s and "\n" not in s else json.dumps(s)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "rule"


def classify(text: str, cfg: Configs, em: _Emitter) -> tuple:
    """(status, tool, rule, title, detail) for one rule sentence, recording any config to emit."""
    langs = cfg.langs
    low = text.lower()

    m = BOUNDARY.search(text)
    if m:
        target, where = m.group(1).strip(), m.group(2).strip()
        jsish = "js" in langs or "/" in target or "/" in where
        if jsish:
            key = f"{where}->{target}"
            enforced = _eslint_on(cfg.eslint, "no-restricted-imports") and target.strip("/*") in cfg.eslint
            if not enforced:
                em.eslint_scoped.append({
                    "files": [where.rstrip("/") + "/**"],
                    "rules": {"no-restricted-imports": ["error", {"patterns": [
                        {"group": [f"**/{target.strip('/').rstrip('*').rstrip('/')}/**", target], "message": text[:200]}]}]},
                })
            return ("enforced" if enforced else "enforceable", "eslint", "no-restricted-imports", f"boundary {key}", {})
        enforced = target in cfg.importlinter and where in cfg.importlinter
        if not enforced:
            em.importlinter.append(
                f"[importlinter:contract:{_slug(where + '-not-' + target)}]\nname = {text[:120]}\ntype = forbidden\n"
                f"source_modules =\n    {where}\nforbidden_modules =\n    {target}\n"
            )
        return ("enforced" if enforced else "enforceable", "import-linter", "forbidden", f"boundary {where}->{target}", {})

    protect = PROTECT.search(text)
    if protect and not re.search(r"\b(?:test|tests)\b", protect.group(1)):
        path = protect.group(1).strip()
        glob = path if any(c in path for c in "*?") else (path.rstrip("/") + "/**" if path.endswith("/") or "." not in
                                                          os.path.basename(path) else path)
        enforced = cfg.trellis_in_ci and path.rstrip("/*") in cfg.trellis
        if not enforced:
            em.trellis_protect.append(glob)
        return ("enforced" if enforced else "enforceable", "trellis", "scope", f"protect {glob}", {})

    for t in CATALOG:
        if not t.pattern.search(low) and not t.pattern.search(text):
            continue
        if t.lang != "any" and langs and t.lang not in langs:
            continue
        if t.lang == "js" and PY_HINT.search(text):
            continue
        tool, rule = t.tool, t.rule
        if tool == "any":
            lang = "py" if langs == ["py"] else "js"
            tool, rule = (ESLINT_MAP_PY if lang == "py" else ESLINT_MAP_JS)[rule]
        if tool == "trellis":
            enforced = cfg.trellis_in_ci and cfg.trellis_levels.get(rule) != "off"
            if not enforced:
                em.trellis_builtins.add(rule)
        elif tool == "eslint":
            needle = "TSEnumDeclaration" if t.key.endswith(":enum") else rule
            enforced = _eslint_on(cfg.eslint, needle)
            if not enforced:
                if t.key.endswith(":enum"):
                    em.eslint_syntax.append({"selector": "TSEnumDeclaration", "message": text[:200]})
                else:
                    em.eslint_rules[rule] = "error"
        else:
            enforced = cfg.ruff_on(rule)
            if not enforced:
                em.ruff_select.append(rule)
        return ("enforced" if enforced else "enforceable", tool, rule, t.title, {})

    m = INSTEAD.search(text)
    if m:
        good, bad = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        return _ban(bad, f"Use `{good}` instead of `{bad}`.", f"Use `{good}`.", text, cfg, em)
    m = BANNED_IMPORT.search(text)
    if m:
        name = (m.group(1) or m.group(2)).strip()
        return _ban_import(name, text, cfg, em)
    m = BANNED_NAME.search(text)
    if m and not PROCESS.search(text):
        name = m.group(1).strip()
        if re.match(r"^[@\w$./()-]+$", name) and len(name) <= 60:
            return _ban(name, f"Do not use `{name}` ({text[:120]})", "", text, cfg, em)
    return ("judgment", "", "", "", {})


def _ban_import(name, text, cfg, em):
    langs = _module_lang(name, cfg.langs)
    if "js" in langs:
        enforced = _eslint_on(cfg.eslint, "no-restricted-imports") and name in cfg.eslint
        if not enforced:
            em.eslint_imports.append({"name": name, "message": text[:200]})
        return ("enforced" if enforced else "enforceable", "eslint", "no-restricted-imports", f"ban import {name}", {})
    enforced = cfg.ruff_on("TID251") and name in cfg.ruff_text
    if not enforced:
        em.ruff_banned[name] = text[:200]
    return ("enforced" if enforced else "enforceable", "ruff", "TID251", f"ban import {name}", {})


def _ban(name, message, fix, text, cfg, em):
    name = name.strip()
    if name.startswith(("-", "#")):  # a CLI flag or a compiler attribute, not something code imports or calls
        return ("judgment", "", "", "", {})
    if re.match(r"^(?:@[\w-]+/)?[\w-]+(?:/[\w-]+)*$", name) and ("/" in name or "-" in name):
        return _ban_import(name, text, cfg, em)
    rid = "no-" + _slug(name)
    pattern = _rx(name)
    enforced = cfg.trellis_in_ci and (rid in cfg.trellis or name in cfg.trellis)
    if not enforced and all(r["id"] != rid for r in em.trellis_rules):
        em.trellis_rules.append({"id": rid, "pattern": pattern, "message": message, "fix": fix or text[:200],
                                 "level": "warn"})
    return ("enforced" if enforced else "enforceable", "trellis", rid, f"ban {name}", {"pattern": pattern})


def audit(target: str = ".", gh=None) -> AuditReport:
    """Audit a local directory, or a GitHub repo given as `owner/repo` or its URL."""
    from .github import parse_repo_ref

    if os.path.isdir(target):
        src = LocalSource(target)
    elif parse_repo_ref(target):
        src = GitHubSource(parse_repo_ref(target), gh)
    else:
        raise FileNotFoundError(f"{target}: not a directory or owner/repo")
    paths = src.list()
    files = [p for p in paths if P.matches(p, INSTRUCTION_GLOBS)]
    files.sort(key=lambda p: (p.count("/"), p))
    cfg = read_configs(paths, src.read)
    em = _Emitter(cfg.langs)
    items = []
    seen = set()
    for f in files:
        text = src.read(f) or ""
        for no, sent in extract_rules(text):
            k = sent.lower()
            if k in seen:
                continue
            seen.add(k)
            if PROCESS.search(sent) and not re.search(r"`[^`]+`", sent):
                items.append(AuditItem(f, no, sent, "judgment"))
                continue
            status, tool, rule, title, detail = classify(sent, cfg, em)
            items.append(AuditItem(f, no, sent, status, tool, rule, title, detail))
    return AuditReport(target, files, items, cfg.langs, em.render())
