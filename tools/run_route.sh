#!/bin/sh
# run_route.sh SCRIPT OUTDIR [VAR=value ...]
# Headless run of one input script with per-frame WRAM (+pixels) dumps.
# Binary defaults to build/UniracersSNESRecomp (override with BIN=...).
set -u
S=$1; O=$2; shift 2
here=$(cd "$(dirname "$0")/.." && pwd)
: "${BIN:=$here/build/UniracersSNESRecomp}"
: "${SNESRECOMP_ROM:=$here/Uniracers (USA).sfc}"
mkdir -p "$O/fd"
env SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy SNESRECOMP_FRAMEDUMP_PIXELS=${PIXELS:-1} "$@" \
  timeout "${TMO:-900}" "$BIN" --no-launcher --script "$S" --framedump "$O/fd" "$SNESRECOMP_ROM" \
  > "$O/log.txt" 2>&1
rc=$?
echo "$S -> $O exit=$rc"
exit $rc
