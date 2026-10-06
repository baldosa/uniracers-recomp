#!/bin/sh
# run_ref.sh SCRIPT OUTDIR -- run a route script on the snes9x oracle (snesref)
# with fresh SRAM; `dump` output lands in OUTDIR/dump. `turbo` lines are
# host-only and dropped (headless snesref is unpaced anyway).
# Needs build-snesref/snesref (see docs) and SNES9X_CORE (default
# ~/.local/cores/snes9x_libretro.so).
set -u
S=$1; O=$2
here=$(cd "$(dirname "$0")/.." && pwd)
: "${SNES9X_CORE:=$HOME/.local/cores/snes9x_libretro.so}"
: "${SNESRECOMP_ROM:=$here/Uniracers (USA).sfc}"
rm -rf "$O"; mkdir -p "$O/dump"; O=$(realpath "$O")
grep -v '^turbo' "$S" > "$O/script.txt"
cd "$O" && SNESREF_HEADLESS=1 SNESREF_WRAM_FILL=0 SNESREF_SCRIPT="$O/script.txt" \
  SNESREF_DUMP_DIR="$O/dump" timeout "${TMO:-900}" "$here/build-snesref/snesref" \
  "$SNES9X_CORE" "$SNESRECOMP_ROM" > "$O/log.txt" 2>&1
rc=$?
echo "$S -> $O exit=$rc"
exit $rc
