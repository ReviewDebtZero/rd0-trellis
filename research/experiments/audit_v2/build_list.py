"""Repos for audit_v2: AIDev repos with at least one agent PR whose diff touches an instruction file,
ranked by agent-PR count; top N are then checked for instruction files at HEAD.
Usage: python build_list.py OUT_CSV [--top 800]"""
import re
import sys

import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem

PAT = re.compile(r"(^|/)(agents\.md|claude\.md|gemini\.md|conventions\.md|\.cursorrules|\.windsurfrules|\.clinerules)$"
                 r"|(^|/)\.cursor/rules/|(^|/)\.github/copilot-instructions\.md$|(^|/)\.github/instructions/", re.IGNORECASE)
fs = HfFileSystem()
D = "datasets/hao-li/AIDev"
top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 800
with fs.open(f"{D}/pull_request.parquet") as f:
    prs = pq.read_table(f, columns=["id", "repo_url"]).to_pandas()
prs["repo"] = prs.repo_url.str.replace("https://api.github.com/repos/", "", regex=False)
hit = set()
with fs.open(f"{D}/pr_commit_details.parquet") as f:
    pf = pq.ParquetFile(f)
    for i in range(pf.metadata.num_row_groups):
        d = pf.read_row_group(i, columns=["pr_id", "filename"]).to_pandas()
        hit.update(int(x) for x in d[d.filename.fillna("").str.contains(PAT)].pr_id.unique())
total = prs.repo.value_counts()
rule_repos = prs[prs.id.isin(hit)].repo.value_counts()
out = total[rule_repos.index].rename("agent_prs").to_frame()
out["rule_file_prs"] = rule_repos
out.sort_values("agent_prs", ascending=False).head(top).to_csv(sys.argv[1], index_label="repo")
print(f"{len(hit)} PRs touch an instruction file, in {len(rule_repos)} repos; wrote top {top}")
