"""Score the RQ1c blinded audit. Usage: python score.py"""
import collections
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VALID = {"checkable": {"y", "n"}, "check_matches": {"y", "partial", "n"}}


def load(name):
    path = os.path.join(HERE, f"labels_{name}.csv")
    if not os.path.exists(path):
        return None
    with open(path, newline="") as f:
        rows = {int(r["id"]): {k: r[k].strip().lower() for k in VALID} for r in csv.DictReader(f)}
    bad = [i for i, r in rows.items() if any(r[k] not in v for k, v in VALID.items())]
    if bad:
        raise SystemExit(f"labels_{name}.csv: missing or invalid labels on ids {bad[:10]}")
    return rows


def precision(labels, key, ok):
    by_tool, wsum, wok = collections.defaultdict(lambda: [0, 0]), 0.0, 0.0
    for i, k in key.items():
        hit = labels[i]["check_matches"] in ok
        by_tool[k["tool"]][0] += hit
        by_tool[k["tool"]][1] += 1
        wsum += k["weight"]
        wok += k["weight"] * hit
    out = {t: {"correct": c, "n": n, "pct": round(100 * c / n, 1)} for t, (c, n) in sorted(by_tool.items())}
    c, n = sum(v[0] for v in by_tool.values()), sum(v[1] for v in by_tool.values())
    out["sample"] = {"correct": c, "n": n, "pct": round(100 * c / n, 1)}
    out["population_weighted_pct"] = round(100 * wok / wsum, 1)
    return out


def kappa(a, b, ids, field):
    n = len(ids)
    po = sum(a[i][field] == b[i][field] for i in ids) / n
    ca, cb = collections.Counter(a[i][field] for i in ids), collections.Counter(b[i][field] for i in ids)
    pe = sum(ca[c] * cb[c] for c in ca) / n / n
    return {"observed_agreement": round(po, 3), "kappa": round((po - pe) / (1 - pe), 3) if pe < 1 else None}


with open(os.path.join(HERE, "sample_key.jsonl")) as f:
    key = {d["id"]: d for d in map(json.loads, f)}
res = {"n": len(key)}
ann = {who: load(who) for who in ("harshul", "devin", "adjudicated")}
for who, labels in ann.items():
    if labels:
        res[who] = {"strict": precision(labels, key, {"y"}), "lenient": precision(labels, key, {"y", "partial"})}
if ann["harshul"] and ann["devin"]:
    ids = sorted(key)
    res["agreement"] = {f: kappa(ann["harshul"], ann["devin"], ids, f) for f in VALID}
    res["disagreements"] = [i for i in ids if ann["harshul"][i]["check_matches"] != ann["devin"][i]["check_matches"]]
out = os.path.join(HERE, "..", "results", "audit_v3", "precision_blinded.json")
with open(out, "w") as f:
    json.dump(res, f, indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "disagreements"}, indent=1))
