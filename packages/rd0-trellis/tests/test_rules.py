from conftest import diff_for
from rd0_trellis import Config, parse_diff, scan
from rd0_trellis.rules import comment_text, looks_like_code


def rules_hit(path, *lines, text=""):
    return [f.rule for f in scan(parse_diff(diff_for(path, list(lines))), text)]


def test_comment_text():
    assert comment_text("a.py", "    # hello there") == "hello there"
    assert comment_text("a.py", "x = 1  # trailing") == "trailing"
    assert comment_text("a.ts", 'const u = "http://x.y"; // note') == "note"
    assert comment_text("a.ts", 'const u = "http://x.y";') is None
    assert comment_text("a.py", "#!/usr/bin/env python") is None


def test_workaround_comment():
    assert rules_hit("a.py", "# workaround: retry because the API flakes") == ["workaround-comment"]
    assert rules_hit("a.ts", "await sleep(500); // to avoid the race error") == ["workaround-comment"]
    assert rules_hit("a.py", "# Retry three times, as the spec requires") == []
    assert rules_hit("README.md", "This is a workaround for now.") == []


def test_bare_suppression():
    assert rules_hit("a.ts", "// @ts-ignore") == ["bare-suppression"]
    assert rules_hit("a.ts", "// eslint-disable-next-line") == ["bare-suppression"]
    assert rules_hit("a.ts", "// eslint-disable-next-line no-console") == ["bare-suppression"]
    assert rules_hit("a.ts", "// eslint-disable-next-line no-console -- CLI prints to stdout") == []
    assert rules_hit("a.ts", "// The CLI prints progress to stdout", "// eslint-disable-next-line no-console") == []
    assert rules_hit("a.ts", "// @ts-expect-error the upstream types miss this overload") == []
    assert rules_hit("a.py", "import foo  # noqa") == ["bare-suppression"]
    assert rules_hit("a.py", "import foo  # noqa: F401") == []
    assert rules_hit("a.py", "x = y  # type: ignore") == ["bare-suppression"]
    assert rules_hit("a.py", "x = y  # type: ignore[attr-defined]") == []
    assert rules_hit("a.go", "x := y //nolint") == ["bare-suppression"]


def test_commented_out_code():
    assert rules_hit("a.ts", "// const legacy = load(user);", "// setTheme(legacy.theme);") == ["commented-out-code"]
    assert rules_hit("a.py", "# old = compute(x)", "# return old") == ["commented-out-code"]
    assert rules_hit("a.ts", "// return early when the user has no theme set") == []
    assert rules_hit("a.py", "# TODO: return a tuple here", "# e.g. foo(1)") == []
    assert looks_like_code("const x = 1;") and not looks_like_code("Load the user, then render the page.")


def test_scope_lockfile_ci_gitignore_docs():
    files = parse_diff(
        diff_for("package-lock.json", ['"version": "1.2.4"'])
        + diff_for(".github/workflows/ci.yml", ["  run: true"])
        + diff_for(".gitignore", [".env"])
        + diff_for("FIX_SUMMARY.md", ["# What I did"], new=True)
        + diff_for("src/app.ts", ["export const a = 1;"])
    )
    hits = {f.path for f in scan(files, "Fix the login button")}
    assert hits == {"package-lock.json", ".github/workflows/ci.yml", ".gitignore", "FIX_SUMMARY.md"}


def test_scope_respects_pr_text():
    files = parse_diff(diff_for("package-lock.json", ["x"]) + diff_for(".github/workflows/ci.yml", ["x"]))
    assert scan(files, "Bump dependencies and update the CI workflow") == []


def test_scope_lockfile_with_manifest_is_fine():
    files = parse_diff(diff_for("package.json", ['"a": "1"']) + diff_for("package-lock.json", ['"a": "1"']))
    assert scan(files, "Add a") == []


def test_scope_outside_named_paths():
    files = parse_diff(
        diff_for("src/auth/login.py", ["x = 1"])
        + diff_for("src/auth/tests/test_login.py", ["x = 1"])
        + diff_for("billing/invoice.py", ["x = 1"])
    )
    hits = [f.path for f in scan(files, "Fix timeout in `src/auth/login.py`")]
    assert hits == ["billing/invoice.py"]


def test_scope_protect_and_allow():
    cfg = Config.from_toml('[trellis.scope]\nprotect = ["src/generated/**"]\nallow = [".gitignore"]')
    files = parse_diff(diff_for("src/generated/api.ts", ["x"]) + diff_for(".gitignore", ["x"]))
    assert [f.path for f in scan(files, "", cfg)] == ["src/generated/api.ts"]


def test_skips_generated_and_vendored():
    files = parse_diff(diff_for("vendor/lib/a.py", ["# workaround for now"]) + diff_for("a.min.js", ["// @ts-ignore"]))
    assert scan(files) == []


def test_custom_rule_paths_and_levels():
    cfg = Config.from_toml(
        "[trellis.rules]\nbare-suppression = \"off\"\n"
        "[[rule]]\nid = \"no-useeffect\"\npattern = '\\buseEffect\\('\npaths = [\"src/**/*.tsx\"]\n"
        "level = \"error\"\nfix = \"Use useSyncedState.\"\nevidence = [\"https://x/1\"]\n"
    )
    files = parse_diff(
        diff_for("src/a/B.tsx", ["useEffect(() => {}, []); // @ts-ignore"]) + diff_for("test/B.tsx", ["useEffect(f)"])
    )
    (f,) = scan(files, "", cfg)
    assert (f.rule, f.level, f.path, f.evidence) == ("no-useeffect", "error", "src/a/B.tsx", ["https://x/1"])


def test_bad_config_is_reported():
    import pytest

    with pytest.raises(ValueError):
        Config.from_toml('[[rule]]\nid = "x"\npattern = "("\n')
    with pytest.raises(ValueError):
        Config.from_toml('[trellis.rules]\nscope = "loud"\n')


def test_scope_honours_ignore_and_protected_renames():
    cfg = Config.from_toml('[trellis]\nignore = ["docs/**"]\n[trellis.scope]\nprotect = ["src/generated/**"]')
    files = parse_diff(
        diff_for("docs/SUMMARY.md", ["# notes"], new=True)
        + "diff --git a/src/generated/api.ts b/src/api.ts\nsimilarity index 100%\n"
        "rename from src/generated/api.ts\nrename to src/api.ts\n"
    )
    assert [f.path for f in scan(files, "", cfg)] == ["src/api.ts"]
