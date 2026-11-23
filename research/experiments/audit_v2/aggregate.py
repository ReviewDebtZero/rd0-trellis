"""Aggregate per-repo `trellis audit --json` files into results/audit_v2/{summary.json,per_repo.csv,checkable.jsonl}.
Usage: python aggregate.py AUDIT_DIR RESULTS_DIR"""
import collections
import csv
import glob
import json
import os
import statistics
import sys

src, dst = sys.argv[1], sys.argv[2]
rows, checkable, by_tool = [], [], collections.Counter()
for f in sorted(glob.glob(os.path.join(src, "*.json"))):
    with open(f) as fh:
        d = json.load(fh)
    repo = os.path.basename(f)[:-5].replace("_", "/", 1)
    rows.append({"repo": repo, "instruction_files": len(d["instruction_files"]), "rules": d["rules"],
                 "enforced": d["enforced"], "enforceable": d["enforceable"], "judgment": d["judgment"]})
    for it in d["items"]:
        if it["status"] != "judgment":
            by_tool[(it["status"], it["tool"])] += 1
            checkable.append({"repo": repo, **{k: it[k] for k in ("status", "tool", "rule", "file", "line", "text")}})
def S(k):
    return sum(r[k] for r in rows)
enf, ena = S("enforced"), S("enforceable")
summary = {"repos": len(rows), "rules": S("rules"), "enforced": enf, "enforceable": ena, "judgment": S("judgment"),
           "checkable_pct": round(100 * (enf + ena) / S("rules"), 2),
           "unenforced_of_checkable_pct": round(100 * ena / (enf + ena), 2),
           "repos_with_checkable": sum(r["enforced"] + r["enforceable"] > 0 for r in rows),
           "repos_with_enforced": sum(r["enforced"] > 0 for r in rows),
           "rules_per_repo_median": statistics.median(r["rules"] for r in rows),
           "by_status_tool": {f"{s}/{t}": n for (s, t), n in sorted(by_tool.items())}}
os.makedirs(dst, exist_ok=True)
with open(os.path.join(dst, "summary.json"), "w") as fh:
    json.dump(summary, fh, indent=2)
with open(os.path.join(dst, "per_repo.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
with open(os.path.join(dst, "checkable.jsonl"), "w") as fh:
    fh.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in checkable)
print(json.dumps(summary, indent=2))
