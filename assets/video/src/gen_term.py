"""Write term.html: a typed replay of the real `trellis audit` and `trellis scan` output in audit.txt / scan.txt."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def color(ln: str) -> str:
    s = ln.strip()
    if s.startswith("ERROR"):
        return "#fca5a5"
    if s.startswith("WARN"):
        return "#fde68a"
    if s.startswith("fix:"):
        return "#86efac"
    if "[eslint" in s or "[trellis" in s:
        return "#c7d2fe"
    return "#e2e8f0"


steps = [["cmd", "uvx rd0-trellis audit examples/repo"]]
steps += [["out", ln, color(ln)] for ln in (HERE / "audit.txt").read_text().splitlines()]
steps += [["gap", 900], ["clear"], ["cmd", "trellis scan agent_pr.diff --config trellis.toml"]]
steps += [["out", ln, color(ln)] for ln in (HERE / "scan.txt").read_text().splitlines()]
page = """<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="scenes/base.css"><style>
.hd{position:absolute;left:120px;top:60px;font-size:46px;font-weight:800}.hd2{position:absolute;left:120px;top:125px;font-size:27px;color:#cbd5e1}
.win{position:absolute;left:120px;right:120px;top:190px;bottom:60px;background:#0b1220;border:2px solid #334155;border-radius:20px;box-shadow:0 30px 70px rgba(0,0,0,.55);overflow:hidden}
.bar{height:52px;background:#111827;border-bottom:1px solid #1f2937;display:flex;align-items:center;gap:12px;padding-left:22px}.bar i{width:16px;height:16px;border-radius:50%}
.bar span{margin-left:20px;color:#64748b;font-size:20px}
#t{padding:24px 32px;font-size:21px;line-height:1.5;white-space:pre}
.p{color:#34d399}.cur{display:inline-block;width:12px;height:25px;background:#e2e8f0;vertical-align:-5px;animation:bl 1s steps(1) infinite}@keyframes bl{50%{opacity:0}}
.grad{background:linear-gradient(90deg,#34d399,#60a5fa);-webkit-background-clip:text;color:transparent}
</style></head><body><div class="bg"></div><div class="dots"></div>
<div class="hd">Trellis: <span class="grad">your AGENTS.md, enforced</span></div>
<div class="hd2">Real output &middot; the example repo and agent PR in packages/rd0-trellis/examples</div>
<div class="win"><div class="bar"><i style="background:#ef4444"></i><i style="background:#f59e0b"></i><i style="background:#22c55e"></i><span class="mono">~/app &mdash; bash</span></div><div id="t" class="mono"></div></div>
<script>
const S=__STEPS__;const t=document.getElementById('t');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{await sleep(600);for(const s of S){if(s[0]==='gap'){await sleep(s[1]);continue}
 if(s[0]==='clear'){t.innerHTML='';continue}
 if(s[0]==='cmd'){const line=document.createElement('div');line.innerHTML='<span class="p">$ </span><span class="c"></span><span class="cur"></span>';t.appendChild(line);const c=line.querySelector('.c');
  for(const ch of s[1]){c.textContent+=ch;await sleep(30)}await sleep(350);line.querySelector('.cur').remove();await sleep(250)}
 else{const d=document.createElement('div');d.style.color=s[2];d.textContent=s[1]||' ';t.appendChild(d);await sleep(/ERROR|WARN|enforced/.test(s[1])?420:150)}}
 const line=document.createElement('div');line.innerHTML='<span class="p">$ </span><span class="cur"></span>';t.appendChild(line)})();
</script></body></html>"""
(HERE / "term.html").write_text(page.replace("__STEPS__", json.dumps(steps)))
print(len(steps), "steps")
