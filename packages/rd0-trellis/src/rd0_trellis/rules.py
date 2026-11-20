"""The checks. Line rules look at added (and, for the ratchet, removed) lines; the scope rule looks at
which files a PR touches."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field

from . import paths as P
from .config import Config, CustomRule
from .diff import FileDiff

DOCS = "https://github.com/harshuljain13/rd0-trellis/blob/main/docs/USERS_GUIDE.md"


@dataclass
class Finding:
    rule: str
    level: str
    path: str
    line: int | None
    message: str
    fix: str = ""
    snippet: str = ""
    evidence: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in ("", None, [])}

    @property
    def where(self) -> str:
        return f"{self.path}:{self.line}" if self.line else self.path


def comment_text(path: str, line: str) -> str | None:
    """The comment part of a source line, or None. Handles whole-line and simple trailing comments."""
    s = line.strip()
    for p in P.comment_prefixes(path):
        if s.startswith(p) and not (p == "*" and s.startswith("*/")):
            if p == "#" and s.startswith(("#!", "#include", "#define", "#if", "#endif", "#pragma", "#import")):
                return None
            body = s[len(p) :].strip()
            for end in ("*/", "-->"):
                body = body.removesuffix(end)
            return body.strip()
    for p in P.comment_prefixes(path):
        if p in ("#", "//", "--"):
            m = re.search(rf"(?<=\s){re.escape(p)}\s", line) if p != "//" else re.search(r"(?<![:\w])//\s", line)
            if m and line[: m.start()].count('"') % 2 == 0 and line[: m.start()].count("'") % 2 == 0:
                return line[m.end() :].strip()
    return None


def whole_comment(path: str, line: str) -> str | None:
    """Comment text when the whole line is a comment, else None."""
    s = line.strip()
    if not any(s.startswith(p) for p in P.comment_prefixes(path)):
        return None
    return comment_text(path, line)


class LineRule:
    id = ""
    default = "warn"
    summary = ""

    def applies(self, path: str) -> bool:
        return P.is_code(path)

    def hits(self, path: str, lines: list) -> list:
        """(line number, snippet, message, fix) for each hit in `lines`, a list of (number, text)."""
        raise NotImplementedError


WORKAROUND = re.compile(
    r"\b(?:work[- ]?around|hack(?:y|ish)?|quick[- ]fix|temp(?:orary)?(?:ily)? fix|band-?aid|kludge|"
    r"monkey[- ]?patch(?:ed|ing)?|for now|just in case|to be safe|as a fallback|"
    r"to (?:avoid|prevent|silence|suppress|bypass|get around) (?:the |this |a |an )?(?:[\w-]+ ){0,2}"
    r"(?:error|issue|warning|crash|failure|lint|type error|test failure)s?|"
    r"(?:silence|suppress|bypass)(?:es|ed|ing)? (?:the |this )?(?:error|warning|lint|type)|"
    r"until (?:\S+ ){0,6}(?:is |are |gets? )?(?:fixed|resolved|merged|released)|"
    r"remove (?:this|me) (?:once|when|after)|fixme|xxx)\b",
    re.IGNORECASE,
)


class WorkaroundComment(LineRule):
    id = "workaround-comment"
    summary = "A new comment explains a workaround instead of fixing the cause."

    def hits(self, path, lines):
        out = []
        for no, text in lines:
            c = comment_text(path, text)
            if c and WORKAROUND.search(c):
                out.append(
                    (
                        no,
                        text.strip(),
                        f'This comment excuses a workaround ("{WORKAROUND.search(c).group(0)}").',
                        "Fix the cause instead. If the workaround must stay, link an issue that tracks removing it; "
                        "if agents keep writing it, ban the pattern with a rule.",
                    )
                )
        return out


_ESLINT = re.compile(r"eslint-disable(?:-next-line|-line)?\b(.*)")
_TS = re.compile(r"@ts-(ignore|nocheck|expect-error)\b(.*)")
_NOQA = re.compile(r"#\s*noqa\b(:?\s*[A-Z]+\d+(?:\s*,\s*[A-Z]+\d+)*)?", re.IGNORECASE)
_TYPE_IGNORE = re.compile(r"#\s*(?:type|pyright):\s*ignore\b(\[[^\]]+\])?")
_NOLINT = re.compile(r"//\s*nolint\b(:\S+)?")
_RUBOCOP = re.compile(r"#\s*rubocop:disable\b(.*)")


def _has_reason(rest: str) -> bool:
    rest = rest.strip().lstrip("-:").strip()
    return len(re.findall(r"[A-Za-z]{2,}", rest)) >= 2


class BareSuppression(LineRule):
    id = "bare-suppression"
    summary = "A new lint or type-check suppression has no reason, or silences everything."

    def hits(self, path, lines):
        out = []
        prev_comment = False
        for no, text in lines:
            msg = None
            m = _ESLINT.search(text)
            if m:
                rules, _, reason = m.group(1).partition("--")
                if not rules.strip().strip("*/").strip():
                    msg = "`eslint-disable` with no rule name turns off every rule."
                elif not _has_reason(reason) and not prev_comment:
                    msg = "`eslint-disable` has no reason."
            m = _TS.search(text)
            if m and not msg:
                if m.group(1) == "ignore":
                    msg = "`@ts-ignore` hides any type error on the next line, including future ones."
                elif m.group(1) == "nocheck":
                    msg = "`@ts-nocheck` turns off type checking for the whole file."
                elif not _has_reason(m.group(2)) and not prev_comment:
                    msg = "`@ts-expect-error` has no reason."
            m = _NOQA.search(text)
            if m and not msg and not m.group(1):
                msg = "Blanket `# noqa` silences every lint rule on this line."
            m = _TYPE_IGNORE.search(text)
            if m and not msg and not m.group(1):
                msg = "Blanket `# type: ignore` hides every type error on this line."
            m = _NOLINT.search(text)
            if m and not msg and not m.group(1):
                msg = "Blanket `//nolint` silences every linter on this line."
            m = _RUBOCOP.search(text)
            if m and not msg and not m.group(1).strip():
                msg = "`rubocop:disable` with no cop name."
            if msg:
                out.append(
                    (
                        no,
                        text.strip(),
                        msg,
                        "Fix the underlying error. If it is a false positive, name the exact rule or code and say why "
                        "(e.g. `// eslint-disable-next-line no-console -- CLI output`).",
                    )
                )
            c = comment_text(path, text)
            prev_comment = bool(c) and c.strip() == text.strip().lstrip("#/-* ").strip() and len(c.split()) >= 3
        return out


_SKIP_COMMENT = re.compile(
    r"^(?:type:|noqa|pragma|pylint|eslint|@ts-|prettier|istanbul|c8|nolint|go:|region|endregion|"
    r"-\*-|todo|note|fixme|see |e\.g\.|i\.e\.|example|usage|>>>|\$ |https?://|@param|@return|@throws|@type|"
    r"<reference|#)",
    re.IGNORECASE,
)
_CODEY = re.compile(
    r"(?:^(?:def |class |return\b|import |from \S+ import |if\s*\(|elif |else\s*[:{]|for\s*\(|for \w+ in |"
    r"while\s*\(|const |let |var |function |async |await |print\(|console\.\w+\(|self\.|this\.|try\s*[:{]|"
    r"except\b|catch\s*\(|throw |raise |package |func |fn |pub |public |private |}\s*else)|"
    r"[;{]\s*$|^\}|^\w[\w.\[\]]*\s*(?:[-+*/]?=)\s*\S|^\w[\w.]*\([^)]*\)\s*;?$)"
)


def looks_like_code(c: str) -> bool:
    if not c or _SKIP_COMMENT.match(c):
        return False
    if not _CODEY.search(c):
        return False
    if re.match(r"^(?:return|import|raise|throw|await) [\w.]+;?$", c):
        return True
    words = re.findall(r"[A-Za-z]{3,}", c)
    symbols = len(re.findall(r"[(){}\[\];=.<>]", c))
    return symbols >= 1 and not (len(words) >= 7 and symbols <= 2)


class CommentedOutCode(LineRule):
    id = "commented-out-code"
    summary = "New code was added already commented out."

    def hits(self, path, lines):
        out, run = [], []

        def flush():
            strong = any(re.search(r"[;{]\s*$", c) for _, _, c in run)
            if len(run) >= 2 or (run and strong):
                no, text, _ = run[0]
                n = len(run)
                out.append(
                    (
                        no,
                        text.strip(),
                        f"{n} line(s) of commented-out code." if n > 1 else "Commented-out code.",
                        "Delete it. Git keeps the history; if it is needed later, restore it from the log.",
                    )
                )
            run.clear()

        last = None
        for no, text in lines:
            c = whole_comment(path, text)
            code = c is not None and looks_like_code(c)
            if not code or (last is not None and no != last + 1):
                flush()
            if code:
                run.append((no, text, c))
            last = no
        flush()
        return out


class CustomLineRule(LineRule):
    def __init__(self, rule: CustomRule):
        self.rule = rule
        self.id = rule.id
        self.default = rule.level
        self.summary = rule.message

    def applies(self, path):
        if self.rule.paths and not P.matches(path, self.rule.paths):
            return False
        return not P.matches(path, self.rule.exclude)

    def hits(self, path, lines):
        out = []
        for no, text in lines:
            if self.rule.regex.search(text):
                out.append((no, text.strip(), self.rule.message or f"Matches rule `{self.id}`.", self.rule.fix))
        return out


BUILTIN_LINE_RULES = (WorkaroundComment, BareSuppression, CommentedOutCode)
BUILTIN_IDS = [r.id for r in BUILTIN_LINE_RULES] + ["scope"]


def line_rules(config: Config) -> list:
    out = []
    for cls in BUILTIN_LINE_RULES:
        r = cls()
        r.level = config.level(r.id, r.default)
        out.append(r)
    for cr in config.rules:
        r = CustomLineRule(cr)
        r.level = config.level(r.id, cr.level)
        out.append(r)
    return [r for r in out if r.level != "off"]


# ---- scope -----------------------------------------------------------------------------------------

_PATHLIKE = re.compile(r"`?([\w.@-]+(?:/[\w.@*-]+)+/?|[\w.-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|md|yml|yaml|json|toml))`?")
_SUMMARY_DOC = re.compile(
    r"(summary|notes?|implementation|changes|plan|report|analysis|solution|fix|walkthrough|overview|todo)",
    re.IGNORECASE,
)


def _mentions(text: str, *words) -> bool:
    return any(re.search(rf"\b{w}", text, re.IGNORECASE) for w in words)


def scope_findings(files: list, pr_text: str, config: Config) -> list:
    level = config.level("scope", "warn")
    if level == "off":
        return []
    changed = {f.path for f in files}
    out = []

    def add(f: FileDiff, msg: str, fix: str):
        out.append(Finding("scope", level, f.path, None, msg, fix))

    for f in files:
        p = f.path
        if P.matches(p, config.scope_allow):
            continue
        if config.scope_protect and P.matches(p, config.scope_protect):
            add(f, "This path is protected in `trellis.toml`; PRs should not change it.",
                "Revert the change to this file, or ask a maintainer to change it.")
            continue
        base = posixpath.basename(p)
        if base in P.LOCKFILES and f.status != "deleted":
            manifest = P.LOCKFILES[base]
            d = posixpath.dirname(p)
            touched = any(
                posixpath.dirname(c) == d and (posixpath.basename(c) == manifest or c.endswith(manifest))
                for c in changed
            )
            if not touched and not _mentions(pr_text, "lock", "dependenc", "upgrade", "bump", "deps"):
                add(f, f"The lockfile changed but `{manifest}` did not, and the PR does not mention dependencies.",
                    "Revert this file. Re-run the install only when you change dependencies on purpose.")
        elif base == ".gitignore" and not _mentions(pr_text, "gitignore", "ignore"):
            add(f, "`.gitignore` changed, and the PR does not say why.",
                "Revert this file unless the PR needs it; ignore local files in `.git/info/exclude` instead.")
        elif P.is_ci_config(p) and not _mentions(pr_text, "ci", "workflow", "pipeline", "github action", "build",
                                                  "actions", "pre-commit", "release"):
            add(f, "CI configuration changed, and the PR does not mention CI.",
                "Revert this file. Changing CI to make a PR pass needs a maintainer's sign-off.")
        elif f.is_new and P.is_doc(p) and base.lower() not in ("readme.md", "changelog.md"):
            mentioned = base.lower() in pr_text.lower() or _mentions(pr_text, "doc", "readme", "guide", "write-?up")
            top_level = "/" not in p
            if not mentioned and (top_level or _SUMMARY_DOC.search(base)):
                add(f, "A new document nobody asked for (agents often leave summaries and notes in the repo).",
                    "Delete it and put the explanation in the PR description.")

    named = {m.rstrip("/") for m in _PATHLIKE.findall(pr_text)}
    named_hits = {c for c in changed if any(c == n or c.startswith(n + "/") or c.endswith("/" + n) for n in named)}
    if named_hits:
        tops = {c.split("/", 1)[0] for c in named_hits}
        flagged = {x.path for x in out}
        for f in files:
            p = f.path
            if p in flagged or p in named_hits or P.matches(p, config.scope_allow):
                continue
            if p.split("/", 1)[0] in tops or re.search(r"(^|/)(tests?|__tests__|spec)(/|$)|[._-](test|spec)\.", p):
                continue
            if P.is_skipped(p) and posixpath.basename(p) not in P.LOCKFILES:
                continue
            add(f, "This file is outside the area the PR description names.",
                "Revert it, or explain in the PR description why this PR has to change it.")
    return out
