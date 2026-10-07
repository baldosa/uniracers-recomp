#!/bin/sh
# coverage_iter.sh PREV NEXT -- one AOT coverage iteration:
# promote PREV's discoveries into recomp/symbols.toml, regenerate with PREV as
# profile seeds, rebuild, then capture NEXT while checking every route against
# baselines/interp0. Exit non-zero if a step or any route check fails.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
cd "$here"
python3 -I tools/promote_roots.py "$1"/*.json "$1"/*.jsonl
bash tools/regen.sh --profiles "$1" 2>&1 | grep -E 'v2_emit: [0-9]+ roots'
cmake --build build -j"$(nproc)" >/dev/null
tools/capture_coverage.sh "$2" baselines/interp0
