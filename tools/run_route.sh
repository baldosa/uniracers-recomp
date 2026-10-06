#!/bin/sh
# run_route.sh SCRIPT OUTDIR [VAR=value ...]
# Headless run of one input script with per-frame WRAM (+pixels) dumps.
# Each run is sealed in OUTDIR: its own config.ini and saves/ (fresh SRAM,
# or a copy of $SRM). Uniracers writes attract/demo counters to SRAM, so
# sharing saves between runs makes every run different.
# Writes fd/crc.txt (per-frame WRAM CRC), BMPs when PIXELS=1 (default 0).
# Binary defaults to build/UniracersSNESRecomp (override with BIN=...).
set -u
S=$(realpath "$1"); O=$2; shift 2
here=$(cd "$(dirname "$0")/.." && pwd)
: "${BIN:=$here/build/UniracersSNESRecomp}"
: "${SNESRECOMP_ROM:=$here/Uniracers (USA).sfc}"
rm -rf "$O"; mkdir -p "$O/fd" "$O/saves"
O=$(realpath "$O")
cp "$here/build/config.ini" "$O/config.ini"
[ -n "${SRM:-}" ] && cp "$SRM" "$O/saves/save.srm"
mkdir -p "$O/dump"
cd "$O" && env SNESRECOMP_DUMP_DIR="$O/dump" SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy SNESRECOMP_FRAMEDUMP_PIXELS=${PIXELS:-0} "$@" \
  timeout "${TMO:-900}" "$BIN" --no-launcher --config "$O/config.ini" --script "$S" \
  --framedump "$O/fd" "$SNESRECOMP_ROM" > "$O/log.txt" 2>&1
rc=$?
# One WRAM CRC per frame; raw WRAM (128 KiB/frame) only with KEEP_WRAM=1.
sed -n 's/.*"crc32_wram": "\(0x[0-9A-F]*\)".*/\1/p' fd/frame_*[0-9].json > fd/crc.txt
[ -n "${KEEP_WRAM:-}" ] || rm -f fd/frame_*_wram.bin
rm -f fd/frame_*[0-9].json
echo "$S -> $O exit=$rc"
exit $rc
