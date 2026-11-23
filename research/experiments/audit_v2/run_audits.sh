#!/bin/bash
# Usage: run_audits.sh REPO_LIST OUT_DIR. Blob-less sparse clone of instruction + lint config files only,
# then a local `trellis audit` (no REST API calls, so no rate limit). 6 repos in parallel.
set -u; LIST=$1; OUT=$2; HERE=$(cd "$(dirname "$0")" && pwd); mkdir -p "$OUT"
one() {
  name=$1; n=$(echo "$name" | tr / _); out="$OUT/$n.json"; [ -s "$out" ] && return
  dir=$(mktemp -d); rm -rf "$dir"
  if timeout 120 git clone -q --depth 1 --filter=blob:none --sparse "https://github.com/$name.git" "$dir" 2>/dev/null; then
    (cd "$dir" && git sparse-checkout set --no-cone --stdin < "$HERE/sparse.txt" && git checkout -q) 2>/dev/null
    timeout 120 trellis audit "$dir" --json > "$out" 2>/dev/null || echo "FAIL $name" >> "$OUT/fails.txt"
  else echo "CLONEFAIL $name" >> "$OUT/fails.txt"; fi
  rm -rf "$dir"
}
export -f one; export OUT HERE
xargs -P6 -I{} bash -c 'one "$1"' _ {} < "$LIST"
