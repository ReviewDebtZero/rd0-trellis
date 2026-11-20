"""Plain-text output for the terminal and Markdown for the PR comment. The comment is written for the
agent that will read it: where, what is wrong, what to do instead."""

from __future__ import annotations

MARKER = "<!-- rd0_trellis:v1 -->"
HOME = "https://github.com/harshuljain13/rd0-trellis"


def text_findings(findings: list, label: str = "") -> str:
    if not findings:
        return f"{label}no findings." if label else "No findings."
    lines = [f"{label}{len(findings)} finding(s)."]
    for f in findings:
        lines.append(f"  {f.level.upper():5} {f.where}  [{f.rule}] {f.message}")
        if f.snippet:
            lines.append(f"        | {f.snippet}")
        if f.fix:
            lines.append(f"        fix: {f.fix}")
        for e in f.evidence:
            lines.append(f"        evidence: {e}")
    return "\n".join(lines)


def debt_line(rc) -> str:
    new = max(rc.net, 0)
    left = "" if rc.remaining is None else f", {rc.remaining} left"
    paid = f", {-rc.net} paid off" if rc.net < 0 else ""
    return f"{rc.rule}: {new} new{paid}{left}"


def text_ratchet(counts: list) -> str:
    if not counts:
        return "No rules to ratchet."
    lines = ["Review debt (count before -> after this change):"]
    for rc in counts:
        mark = "FAIL" if rc.failed else ("warn" if rc.net > 0 else " ok ")
        lines.append(f"  {mark}  {rc.level:5}  {debt_line(rc)}  (+{rc.added} / -{rc.removed})")
    failed = [rc.rule for rc in counts if rc.failed]
    lines.append(f"{len(failed)} rule(s) failed: {', '.join(failed)}" if failed else "No error-level rule got worse.")
    return "\n".join(lines)


def _md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def markdown(findings: list, counts: list | None = None, max_items: int = 30) -> str:
    counts = counts or []
    failed = [rc for rc in counts if rc.failed]
    debt = [rc for rc in counts if rc.added or rc.removed or rc.remaining]
    if not findings and not failed:
        lines = [MARKER, "**Trellis:** nothing to fix. ✅"]
        if debt:
            lines += ["", "Review debt: " + "; ".join(debt_line(rc) for rc in debt)]
        return "\n".join(lines)
    head = f"**Trellis:** {len(findings)} thing(s) to fix before a human reviews this PR"
    if failed:
        head += f"; {len(failed)} rule(s) set to `error` got worse"
    lines = [MARKER, head + ".", ""]
    for f in findings[:max_items]:
        lines.append(f"- **`{f.where}`** `{f.rule}`: {_md_escape(f.message)}")
        if f.snippet:
            lines.append(f"  <br>`{_md_escape(f.snippet[:120])}`")
        if f.fix:
            lines.append(f"  <br>**Fix:** {_md_escape(f.fix)}")
        if f.evidence:
            lines.append("  <br>Why this rule exists: " + " ".join(f"[{i + 1}]({e})" for i, e in enumerate(f.evidence[:5])))
    if len(findings) > max_items:
        lines.append(f"- …and {len(findings) - max_items} more. Run `trellis scan` locally for the full list.")
    if debt:
        lines += ["", "**Review debt:** " + "; ".join(debt_line(rc) for rc in debt)]
    lines += [
        "",
        f"<sub>Coding agents: fix these in this PR, then push. Rules live in `trellis.toml`. "
        f"[rd0-trellis]({HOME}): stop reviewing the same mistake twice.</sub>",
    ]
    return "\n".join(lines)
