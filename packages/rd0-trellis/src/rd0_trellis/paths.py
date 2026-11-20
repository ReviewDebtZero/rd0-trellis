"""File classification shared by the checks."""

from __future__ import annotations

import functools
import posixpath
import re

LOCKFILES = {
    "package-lock.json": "package.json",
    "npm-shrinkwrap.json": "package.json",
    "yarn.lock": "package.json",
    "pnpm-lock.yaml": "package.json",
    "bun.lockb": "package.json",
    "bun.lock": "package.json",
    "poetry.lock": "pyproject.toml",
    "uv.lock": "pyproject.toml",
    "pdm.lock": "pyproject.toml",
    "Pipfile.lock": "Pipfile",
    "Cargo.lock": "Cargo.toml",
    "Gemfile.lock": "Gemfile",
    "go.sum": "go.mod",
    "composer.lock": "composer.json",
    "packages.lock.json": ".csproj",
    "pubspec.lock": "pubspec.yaml",
    "mix.lock": "mix.exs",
    "Podfile.lock": "Podfile",
}

GENERATED = [
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.snap",
    "*.pb.go",
    "*_pb2.py",
    "*_pb2_grpc.py",
    "*.generated.*",
    "*.g.dart",
    "*.svg",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.pdf",
]
VENDORED_DIRS = ("vendor/", "node_modules/", "third_party/", "dist/", "build/", "__generated__/", ".yarn/")

COMMENT_STYLES = {
    "#": {".py", ".rb", ".sh", ".bash", ".zsh", ".pl", ".r", ".toml", ".yaml", ".yml", ".ex", ".exs",
          ".cfg", ".ini", ".tf", ".ps1", ".jl", ".nim", ".cmake", ".dockerfile", ".mk"},
    "//": {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt", ".kts", ".scala", ".go", ".rs",
           ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".swift", ".dart", ".php", ".groovy", ".gradle",
           ".m", ".mm", ".proto", ".sol", ".zig", ".v", ".scss", ".less"},
    "--": {".sql", ".lua", ".hs", ".elm", ".ada"},
}
CODE_EXT = set().union(*COMMENT_STYLES.values()) - {".toml", ".yaml", ".yml", ".cfg", ".ini"}
NAMED = {"Dockerfile": "#", "Makefile": "#", "Rakefile": "#", "Gemfile": "#", "BUILD": "#"}


def ext(path: str) -> str:
    return posixpath.splitext(path)[1].lower()


def comment_prefixes(path: str) -> tuple:
    base = posixpath.basename(path)
    if base in NAMED:
        return (NAMED[base],)
    e = ext(path)
    out = tuple(p for p, exts in COMMENT_STYLES.items() if e in exts)
    if e == ".php":
        out += ("#",)
    if e in {".css", ".scss", ".less", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".go", ".rs",
             ".cs", ".swift", ".kt", ".php", ".h", ".hpp", ".mjs", ".cjs"}:
        out += ("/*", "*")
    if e in {".html", ".vue", ".svelte", ".xml", ".md"}:
        out += ("<!--",)
    if e in {".vue", ".svelte"}:
        out += ("//",)
    return out


def is_code(path: str) -> bool:
    return ext(path) in CODE_EXT or posixpath.basename(path) in NAMED or ext(path) in {".vue", ".svelte"}


@functools.lru_cache(maxsize=512)
def _glob(pattern: str):
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def matches(path: str, patterns) -> bool:
    """Glob match with `**` support. A pattern with no `/` also matches the file name alone."""
    for p in patterns:
        if _glob(p.rstrip("/") + ("/**" if p.endswith("/") else "")).match(path):
            return True
        if "/" not in p and _glob(p).match(posixpath.basename(path)):
            return True
    return False


def is_skipped(path: str, extra=()) -> bool:
    """Generated, vendored, binary and lock files that checks should not read line by line."""
    p = path.replace("\\", "/")
    if any(p.startswith(d) or f"/{d}" in p for d in VENDORED_DIRS):
        return True
    return posixpath.basename(p) in LOCKFILES or matches(p, GENERATED) or matches(p, extra)


def is_ci_config(path: str) -> bool:
    p = path.replace("\\", "/")
    return (
        p.startswith((".github/workflows/", ".circleci/", ".buildkite/"))
        or p in {".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml", "Jenkinsfile", "bitbucket-pipelines.yml",
                 ".circleci/config.yml", "appveyor.yml", ".pre-commit-config.yaml"}
    )


def is_doc(path: str) -> bool:
    return ext(path) in {".md", ".rst", ".txt", ".adoc", ".mdx"} and not posixpath.basename(path).lower().startswith(
        ("requirements", "constraints", "license", "notice", "cmakelists")
    )
