#!/bin/sh
# routes.sh OUTROOT [REFROOT] [VAR=value ...]
# Run every tests/routes/*.txt into OUTROOT/<route>/; with REFROOT, compare
# each run's per-frame WRAM CRCs against REFROOT/<route>/ (exit 1 on any diff).
# Raw dumps go to $SCRATCH (default /tmp) and only crc.txt + log.txt are kept.
set -u
here=$(cd "$(dirname "$0")/.." && pwd)
out=$1; shift
ref=""; case "${1:-}" in *=*|"") ;; *) ref=$1; shift ;; esac
tmp=$(mktemp -d "${SCRATCH:-/tmp}/routes.XXXXXX")
mkdir -p "$out"; fail=0
for s in "$here"/tests/routes/*.txt; do
  r=$(basename "$s" .txt)
  "$here/tools/run_route.sh" "$s" "$tmp/$r" "$@" >/dev/null || { echo "$r: run failed"; fail=1; }
  mkdir -p "$out/$r"; cp "$tmp/$r/fd/crc.txt" "$tmp/$r/log.txt" "$out/$r/"; rm -rf "$tmp/$r"
  if [ -n "$ref" ]; then
    printf '%s: ' "$r"; python3 -I "$here/tools/firstdiff.py" "$ref/$r" "$out/$r" || fail=1
  else
    echo "$r: $(wc -l < "$out/$r/crc.txt") frames"
  fi
done
rmdir "$tmp"
exit $fail
