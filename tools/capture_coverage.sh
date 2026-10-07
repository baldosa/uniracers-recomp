#!/bin/sh
# capture_coverage.sh OUTDIR [BASELINE] -- run every route with Tier-2
# coverage capture on the current build; writes OUTDIR/<route>.json + .jsonl
# and prints each route's interpreted work (instructions still running on the
# interpreter). With BASELINE (e.g. baselines/interp0) each route's dump
# checkpoints are also checked with compare_dumps.py; exit 1 on any failure.
set -u
here=$(cd "$(dirname "$0")/.." && pwd)
out=$(mkdir -p "$1" && realpath "$1")
base=${2:-}
fail=0
tmp=$(mktemp -d "${SCRATCH:-/tmp}/cov.XXXXXX")
for s in "$here"/tests/routes/*.txt; do
  r=$(basename "$s" .txt)
  TMO=${TMO:-1800} "$here/tools/run_route.sh" "$s" "$tmp/$r" SNESRECOMP_TIER2_CAPTURE=1 \
    SNESRECOMP_TIER2_MANIFEST="$out/$r.json" SNESRECOMP_TIER2_JOURNAL="$out/$r.jsonl" >/dev/null \
    || { echo "$r: run FAILED"; fail=1; }
  printf '%s: ' "$r"
  # A run with no interpreter transfers writes no journal.
  python3 "$here/snesrecomp/tools/tier2_ingest.py" "$out/$r.json" $( [ -f "$out/$r.jsonl" ] && echo "$out/$r.jsonl" ) \
    --cfg-dir "$here/recomp" --program-manifest "$here/src/gen/program_manifest.json" 2>&1 \
    | sed -n 's/^Interpreted work: //p'
  if [ -n "$base" ]; then
    python3 -I "$here/tools/compare_dumps.py" "$here/$base/$r" "$tmp/$r" > "$tmp/cmp.txt" || fail=1
    sed 's/^/    /' "$tmp/cmp.txt"; rm -f "$tmp/cmp.txt"
  fi
  rm -rf "$tmp/$r"
done
rmdir "$tmp"
exit $fail
