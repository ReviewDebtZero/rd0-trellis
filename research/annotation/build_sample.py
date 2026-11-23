"""Draw the blinded RQ1c sample from per-repo audit JSON (audit_v3 run) and write the labeling sheets.
Usage: python build_sample.py AUDIT_DIR REPO_LIST"""
import collections
import csv
import glob
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
QUOTA = {"trellis": 100, "eslint": 70, "ruff": 30}
PER_REPO_CAP = 3
SEED = 20261123

seen = set()
with open(os.path.join(HERE, "..", "results", "audit_v2", "precision_spotcheck.jsonl")) as f:
    for line in f:
        d = json.loads(line)
        seen.add((d["repo"].replace("/", "_"), d["file"], d["text"]))

with open(sys.argv[2]) as f:
    names = {n.strip().replace("/", "_"): n.strip() for n in f if n.strip()}
pool = collections.defaultdict(list)
for path in sorted(glob.glob(os.path.join(sys.argv[1], "*.json"))):
    repo = os.path.basename(path)[:-5]
    with open(path) as f:
        rep = json.load(f)
    if not rep.get("instruction_files"):
        continue
    for it in rep["items"]:
        if it["status"] == "judgment" or (repo, it["file"], it["text"]) in seen:
            continue
        pool[it["tool"]].append(dict(it, repo=repo))

rng = random.Random(SEED)
sample = []
for tool, n in QUOTA.items():
    items = pool[tool][:]
    rng.shuffle(items)
    per_repo, picked = collections.Counter(), []
    for it in items:
        if per_repo[it["repo"]] < PER_REPO_CAP:
            per_repo[it["repo"]] += 1
            picked.append(it)
        if len(picked) == n:
            break
    for it in picked:
        it["weight"] = len(pool[tool]) / len(picked)
    sample += picked
rng.shuffle(sample)


def check_text(it):
    s = f"{it['tool']}: {it['rule']}"
    if it.get("title"):
        s += f" ({it['title']})"
    pat = (it.get("detail") or {}).get("pattern")
    if pat:
        s += f" | flags added lines matching /{pat}/"
    return s


with open(os.path.join(HERE, "sample_key.jsonl"), "w") as f:
    for i, it in enumerate(sample, 1):
        f.write(json.dumps({"id": i, "repo": names[it["repo"]], "file": it["file"], "line": it["line"],
                            "text": it["text"], "tool": it["tool"], "rule": it["rule"], "status": it["status"],
                            "check": check_text(it), "pool": len(pool[it["tool"]]),
                            "weight": round(it["weight"], 4)}) + "\n")
with open(os.path.join(HERE, "labels_template.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "repo", "file", "statement", "proposed_check", "checkable", "check_matches", "notes"])
    for i, it in enumerate(sample, 1):
        w.writerow([i, names[it["repo"]], it["file"], it["text"], check_text(it), "", "", ""])
print({t: len(p) for t, p in pool.items()}, collections.Counter(it["tool"] for it in sample))
