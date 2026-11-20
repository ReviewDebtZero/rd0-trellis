from rd0_trellis import action
from rd0_trellis.report import MARKER


class FakeGH:
    def __init__(self, files, comments=(), config=None):
        self.files, self.comments, self.config, self.posted = files, list(comments), config, []

    def pages(self, path, limit):
        if path.endswith("/files"):
            return self.files
        if "/comments" in path:
            return self.comments
        return []

    def read(self, path, ref=None):
        return self.config if path == "trellis.toml" else None

    def call(self, method, path, body=None):
        self.posted.append((method, path, body))


EVENT = {"pull_request": {"number": 7, "title": "Fix login", "body": "", "base": {"sha": "abc"}}}
BAD = [{"filename": "src/a.ts", "status": "modified", "patch": "@@ -1 +1,2 @@\n x\n+// @ts-ignore"}]
CLEAN = [{"filename": "src/a.ts", "status": "modified", "patch": "@@ -1 +1,2 @@\n x\n+const y = 2;"}]


def test_posts_one_comment():
    gh = FakeGH(BAD)
    body, failed = action.run(EVENT, gh)
    assert MARKER in body and not failed
    assert gh.posted[0][:2] == ("POST", "/issues/7/comments")


def test_edits_existing_comment_and_goes_quiet():
    gh = FakeGH(CLEAN, comments=[{"id": 9, "body": MARKER + "\nold", "user": {"type": "Bot"}}])
    body, _ = action.run(EVENT, gh)
    assert "nothing to fix" in body and gh.posted[0][:2] == ("PATCH", "/issues/comments/9")
    gh = FakeGH(CLEAN)
    assert action.run(EVENT, gh) == (None, False) and gh.posted == []


def test_error_rule_from_base_branch_config_fails():
    cfg = "[[rule]]\nid = \"no-ts-ignore\"\npattern = '@ts-ignore'\nlevel = \"error\"\n"
    gh = FakeGH(BAD, config=cfg)
    body, failed = action.run(EVENT, gh)
    assert failed and "no-ts-ignore" in body


def test_ignores_marker_pasted_by_a_person():
    gh = FakeGH(BAD, comments=[{"id": 3, "body": MARKER, "user": {"type": "User"}}])
    action.run(EVENT, gh)
    assert gh.posted[0][:2] == ("POST", "/issues/7/comments")
