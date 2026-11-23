import os

from conftest import EXAMPLES
from rd0_trellis import Config, audit
from rd0_trellis.audit import extract_rules


def test_example_repo_audit():
    r = audit(os.path.join(EXAMPLES, "repo"))
    assert r.files == ["AGENTS.md"]
    by_text = {i.text.split(";")[0]: i for i in r.items}
    assert by_text["Never use `console.log` in product code"].status == "enforced"
    assert by_text["Do not use `any`. Model the type or use `unknown`."].rule == "@typescript-eslint/no-explicit-any"
    assert by_text["Never import from `src/main` in `src/renderer`."].rule == "no-restricted-imports"
    assert by_text["Don't add the `lodash` package"].rule == "no-restricted-imports"
    assert by_text["Don't edit `src/generated/`"].rule == "scope"
    assert by_text["Use `useSyncedState` instead of `useEffect` for derived state."].rule == "no-useeffect"
    assert by_text["Write clear commit messages."].status == "judgment"
    assert r.count("enforced") == 1 and r.count("judgment") == 3 and r.count("enforceable") == 9
    assert "13 rules" in r.headline() and "1 enforced" in r.headline()


def test_emitted_config_is_valid():
    r = audit(os.path.join(EXAMPLES, "repo"))
    assert '"src/renderer/**"' in r.emitted["eslint.config.js"]
    assert '"no-console"' not in r.emitted["eslint.config.js"]
    assert r.emitted["eslint.config.js"].count('"name": "lodash"') == 2
    cfg = Config.from_toml(r.emitted["trellis.toml"])
    assert cfg.scope_protect == ["src/generated/**"]
    assert [x.id for x in cfg.rules] == ["no-useeffect"] and cfg.rules[0].regex.search("useEffect(() => {})")


def test_python_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.ruff.lint]\nselect = ["E", "F", "T20"]\n')
    (tmp_path / "CLAUDE.md").write_text(
        "- Never use `print()`; use logging.\n- No bare except.\n- Do not import `requests`; use `httpx`.\n"
        "- Prefer readable code.\n"
    )
    r = audit(str(tmp_path))
    status = {i.rule: i.status for i in r.items if i.rule}
    assert status == {"T201": "enforced", "E722": "enforced", "TID251": "enforceable"}
    assert '"requests".msg' in r.emitted["pyproject.toml"]


def test_extract_rules_skips_code_and_headings():
    text = "---\ndescription: x\n---\n# Rules\n```\nnever run this\n```\n- Always use strict mode.\nIntro text here.\n"
    assert extract_rules(text) == [(8, "Always use strict mode.")]


def test_no_instruction_files(tmp_path):
    r = audit(str(tmp_path))
    assert r.items == [] and "No agent instruction files" in r.headline()


def test_disabled_rules_are_not_enforced(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "eslint.config.js").write_text("export default [{ rules: { 'no-console': 'off', eqeqeq: ['error'] } }];")
    (tmp_path / "trellis.toml").write_text("[trellis]\nrules = { commented-out-code = 'off' }\n")
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "t.yml").write_text("uses: harshuljain13/rd0-trellis@main\n")
    (tmp_path / "AGENTS.md").write_text("- Never use console.log.\n- Always use strict equality (===).\n"
                                        "- Do not leave commented-out code.\n")
    status = {i.rule: i.status for i in audit(str(tmp_path)).items}
    assert status == {"no-console": "enforceable", "eqeqeq": "enforced", "commented-out-code": "enforceable"}


def test_boundaries_on_one_directory_merge(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "AGENTS.md").write_text("- Never import from `src/main` in `src/renderer`.\n"
                                        "- Never import from `src/server` in `src/renderer`.\n")
    js = audit(str(tmp_path)).emitted["eslint.config.js"]
    assert js.count('"files"') == 1 and "src/main" in js and "src/server" in js


def test_ruff_select_semantics(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("- No bare except.\n- Never use `print()`.\n")
    (tmp_path / "ruff.toml").write_text('[lint]\nextend-select = ["T20"]\n')
    assert {i.rule: i.status for i in audit(str(tmp_path)).items} == {"E722": "enforced", "T201": "enforced"}
    (tmp_path / "ruff.toml").write_text("[lint]\nselect = []\n")
    assert {i.status for i in audit(str(tmp_path)).items} == {"enforceable"}


def test_nested_trellis_toml_does_not_override_root_levels(tmp_path):
    (tmp_path / "trellis.toml").write_text('[trellis.rules]\ncommented-out-code = "off"\n')
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "trellis.toml").write_text('[trellis.rules]\ncommented-out-code = "warn"\n')
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "t.yml").write_text("uses: harshuljain13/rd0-trellis@main\n")
    (tmp_path / "AGENTS.md").write_text("- Do not leave commented-out code.\n")
    assert [i.status for i in audit(str(tmp_path)).items] == ["enforceable"]


def test_misclassifications_from_aidev_spot_check(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    lines = [
        "In non-test code, prefer using `crate` in `use` directives instead of the crate name",
        "No abbreviations like `exe` — use `exec` or full words.",
        "Never add test-only exports (`now`, `delay`). Use `setSystemTime` from `bun:test`.",
        "Do NOT use `--no-build` when testing.",
        "Never add `#[allow(clippy::too_many_arguments)]` to a function.",
        "Do not add `PRIMARY KEY` constraints to bulk tables.",
        "Fully typed. No `Any` or coarse types like `dict[str, Any]`.",
        "Skip with `describe.skipIf(process.env.SKIP === 'true')` when needed.",
        "Pre-existing bugs are out of scope.",
        "Leave pre-existing dead code alone unless asked.",
        "Do not add the `lodash` package.",
        "Never use `as any` to override private methods.",
    ]
    (tmp_path / "AGENTS.md").write_text("".join(f"- {x}\n" for x in lines))
    r = audit(str(tmp_path))
    got = {i.text: (i.status, i.rule) for i in r.items}
    for x in lines[:10]:
        assert got[x][0] == "judgment", (x, got[x])
    assert got[lines[10]][1] == "no-restricted-imports"
    assert got[lines[11]][1] == "@typescript-eslint/no-explicit-any"
