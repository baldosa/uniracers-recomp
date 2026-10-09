#!/bin/sh
# routes.sh OUTROOT [REFROOT] [VAR=value ...]
# Run every tests/routes/*.txt into OUTROOT/<route>/ (crc.txt, log.txt and the
# script's dump checkpoints). A run fails if the binary exits non-zero (an
# `until` gate timing out exits 3). With REFROOT, each route's checkpoints are
# compared against REFROOT/<route>/ with compare_dumps.py (ALLOW=n bytes).
# REF=1 runs the snes9x oracle (run_ref.sh) instead of the recomp binary.
set -u
here=$(cd "$(dirname "$0")/.." && pwd)
out=$1; shift
ref=""; case "${1:-}" in *=*|"") ;; *) ref=$1; shift ;; esac
tmp=$(mktemp -d "${SCRATCH:-/tmp}/routes.XXXXXX")
mkdir -p "$out"; fail=0
for s in "$here"/tests/routes/*.txt; do
  r=$(basename "$s" .txt)
  if [ -n "${REF:-}" ]; then "$here/tools/run_ref.sh" "$s" "$tmp/$r" >/dev/null
  else "$here/tools/run_route.sh" "$s" "$tmp/$r" "$@" >/dev/null; fi
  rc=$?
  rm -rf "$out/$r"; mkdir -p "$out/$r/dump"
  cp "$tmp/$r/log.txt" "$out/$r/"
  [ -f "$tmp/$r/fd/crc.txt" ] && cp "$tmp/$r/fd/crc.txt" "$out/$r/"
  cp "$tmp/$r"/dump/*.wram.bin "$tmp/$r"/dump/*.sram.bin "$tmp/$r"/dump/*.oam.bin "$out/$r/dump/" 2>/dev/null
  rm -rf "$tmp/$r"
  if [ $rc -ne 0 ]; then echo "$r: run FAILED (exit $rc)"; fail=1; continue; fi
  if [ -n "$ref" ]; then
    echo "== $r"; python3 -I "$here/tools/compare_dumps.py" "$ref/$r" "$out/$r" || fail=1
  else
    echo "$r: ok"
  fi
done
rmdir "$tmp"
exit $fail
