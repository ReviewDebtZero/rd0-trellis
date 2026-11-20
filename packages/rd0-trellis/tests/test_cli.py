import json
import os

from conftest import EXAMPLES
from rd0_trellis.cli import main

DIFF = os.path.join(EXAMPLES, "agent_pr.diff")
CFG = os.path.join(EXAMPLES, "trellis.toml")


def test_scan_text_and_exit_codes(capsys):
    assert main(["scan", DIFF, "--config", CFG]) == 1
    out = capsys.readouterr().out
    assert "6 finding(s)" in out and "[no-useeffect]" in out
    assert main(["scan", DIFF]) == 0


def test_scan_json(capsys):
    main(["scan", DIFF, "--json"])
    d = json.loads(capsys.readouterr().out)
    assert d["files"] == 3 and {f["rule"] for f in d["findings"]} >= {"scope", "bare-suppression"}


def test_check(capsys):
    assert main(["check", DIFF, "--config", CFG, "--root", os.path.join(EXAMPLES, "repo")]) == 1
    assert "no-useeffect: 1 new" in capsys.readouterr().out
    assert main(["check", DIFF]) == 0


def test_audit(capsys, tmp_path):
    assert main(["audit", os.path.join(EXAMPLES, "repo"), "--write", str(tmp_path)]) == 0
    assert "13 rules" in capsys.readouterr().out
    assert (tmp_path / "trellis.toml.trellis").exists()


def test_check_fails_on_error_scope(tmp_path):
    (tmp_path / "t.toml").write_text('[trellis.rules]\nscope = "error"\n[trellis.scope]\nprotect = ["src/renderer/**"]\n')
    assert main(["check", DIFF, "--config", str(tmp_path / "t.toml")]) == 1
