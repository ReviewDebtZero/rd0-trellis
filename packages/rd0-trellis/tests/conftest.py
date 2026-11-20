import os

HERE = os.path.dirname(__file__)
EXAMPLES = os.path.join(HERE, "..", "examples")


def diff_for(path: str, added=(), removed=(), new=False) -> str:
    head = f"diff --git a/{path} b/{path}\n"
    head += "new file mode 100644\n--- /dev/null\n" if new else f"--- a/{path}\n"
    head += f"+++ b/{path}\n@@ -1,{len(removed)} +1,{len(added)} @@\n"
    return head + "".join(f"-{x}\n" for x in removed) + "".join(f"+{x}\n" for x in added)
