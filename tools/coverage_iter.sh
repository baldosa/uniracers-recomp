#!/bin/bash
# coverage_iter.sh PREV NEXT -- one AOT coverage iteration:
# promote PREV's discoveries into recomp/symbols.toml, regenerate seeded by
# every capture directory so far (coverage/it*), rebuild, then capture NEXT
# while checking every route against baselines/interp0.
# Exit non-zero if a step or any route check fails.
set -euo pipefail
prev=$1; next=$2
here=$(cd "$(dirname "$0")/.." && pwd)
cd "$here"
python3 -I tools/promote_roots.py "$prev"/*.json "$prev"/*.jsonl
seeds=()
for d in $(ls -d coverage/it* | sort -V); do seeds+=(--profiles "$d"); done
bash tools/regen.sh --cfg-roots "${seeds[@]}" 2>&1 | grep -E 'v2_emit: [0-9]+ roots'
cmake --build build -j"$(nproc)" >/dev/null 2>&1
tools/capture_coverage.sh "$next" baselines/interp0
