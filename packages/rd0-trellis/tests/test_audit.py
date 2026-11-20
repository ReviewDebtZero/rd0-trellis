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
