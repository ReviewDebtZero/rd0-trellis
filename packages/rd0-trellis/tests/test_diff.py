from conftest import diff_for
from rd0_trellis.diff import from_github_files, parse_diff


def test_parse_diff_lines_and_status():
    text = diff_for("a.py", added=["x = 1", "y = 2"], removed=["x = 0"]) + diff_for("NOTES.md", ["hi"], new=True)
    a, b = parse_diff(text)
    assert a.path == "a.py" and a.status == "modified"
    assert a.added == [(1, "x = 1"), (2, "y = 2")] and a.removed == [(1, "x = 0")]
    assert b.path == "NOTES.md" and b.is_new


def test_parse_diff_line_numbers_follow_context():
    text = "diff --git a/f.js b/f.js\n--- a/f.js\n+++ b/f.js\n@@ -10,3 +10,4 @@\n ctx\n+added\n ctx\n-gone\n"
    (f,) = parse_diff(text)
    assert f.added == [(11, "added")] and f.removed == [(12, "gone")]


def test_rename_and_delete():
    text = (
        "diff --git a/old.py b/new.py\nsimilarity index 90%\nrename from old.py\nrename to new.py\n"
        "diff --git a/gone.py b/gone.py\ndeleted file mode 100644\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"
    )
    r, d = parse_diff(text)
    assert (r.path, r.old_path, r.status) == ("new.py", "old.py", "renamed")
    assert d.status == "deleted" and d.removed == [(1, "x")]


def test_from_github_files():
    (f,) = from_github_files([{"filename": "src/a.ts", "status": "added", "patch": "@@ -0,0 +1 @@\n+const a = 1;"}])
    assert f.path == "src/a.ts" and f.is_new and f.added == [(1, "const a = 1;")]


def test_content_that_looks_like_headers():
    text = (
        "diff --git a/q.sql b/q.sql\n--- a/q.sql\n+++ b/q.sql\n@@ -1,2 +1,2 @@\n"
        "--- old comment\n+++ count;\n-x\n+y\n"
        "--- a/plain.py\n+++ b/plain.py\n@@ -1 +1 @@\n-a\n+b\n"
    )
    q, plain = parse_diff(text)
    assert q.path == "q.sql" and q.removed == [(1, "-- old comment"), (2, "x")] and q.added == [(1, "++ count;"), (2, "y")]
    assert plain.path == "plain.py" and plain.added == [(1, "b")]
