import os

from conftest import EXAMPLES, diff_for
from rd0_trellis import Config, parse_diff, ratchet
from rd0_trellis.report import MARKER, markdown

CFG = Config.from_toml("[[rule]]\nid = \"no-print\"\npattern = '\\bprint\\('\nlevel = \"error\"\n")


def by_rule(counts):
    return {rc.rule: rc for rc in counts}


def test_new_violation_fails():
    rc = by_rule(ratchet(parse_diff(diff_for("a.py", ["print(1)"])), CFG))["no-print"]
    assert (rc.added, rc.removed, rc.net, rc.failed) == (1, 0, 1, True)


def test_moved_code_is_not_new():
    text = diff_for("a.py", removed=["print(1)"]) + diff_for("b.py", added=["print(1)"])
    rc = by_rule(ratchet(parse_diff(text), CFG))["no-print"]
    assert rc.net == 0 and not rc.failed


def test_paying_down_debt():
    rc = by_rule(ratchet(parse_diff(diff_for("a.py", removed=["print(1)", "print(2)"])), CFG))["no-print"]
    assert rc.net == -2 and not rc.failed


def test_warn_rules_never_fail():
    counts = ratchet(parse_diff(diff_for("a.ts", ["// @ts-ignore"])))
    assert by_rule(counts)["bare-suppression"].net == 1 and not any(rc.failed for rc in counts)


def test_remaining_counts_the_tree(tmp_path):
    (tmp_path / "x.py").write_text("print(1)\nprint(2)\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "y.py").write_text("print(3)\n")
    rc = by_rule(ratchet([], CFG, root=str(tmp_path)))["no-print"]
    assert rc.remaining == 2


def test_markdown_comment():
    from rd0_trellis import scan

    with open(os.path.join(EXAMPLES, "agent_pr.diff")) as fh:
        files = parse_diff(fh.read())
    cfg = Config.load(os.path.join(EXAMPLES, "trellis.toml"))
    body = markdown(scan(files, "Load theme", cfg), ratchet(files, cfg))
    assert body.startswith(MARKER)
    assert "**`src/renderer/Settings.tsx:9`** `no-useeffect`" in body
    assert "**Fix:**" in body and "Why this rule exists: [1](" in body
    assert "no-useeffect: 1 new" in body
    clean = markdown([], [])
    assert "nothing to fix" in clean
