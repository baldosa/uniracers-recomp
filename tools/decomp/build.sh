#!/usr/bin/env bash
# Regenerate the disassembly and rebuild it; succeed only if byte-identical.
# usage: tools/decomp/build.sh [ROM]   (default: "Uniracers (USA).sfc")
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROM="$(realpath "${1:-$ROOT/Uniracers (USA).sfc}")"
ASAR="${ASAR:-$(command -v asar || echo ~/.local/bin/asar)}"
cd "$ROOT"
mkdir -p build/decomp
ln -sf "$ROM" build/baserom.sfc
[ -f build/decomp/decode.json ] || python3 tools/decomp/decode_dump.py "$ROM" build/decomp/decode.json
rm -rf build/disasm  # a stale file from an older layout must not linger
python3 tools/decomp/gen_disasm.py "$ROM" build/decomp/decode.json build/disasm
(cd build/disasm && "$ASAR" --fix-checksum=off main.asm ../decomp/uniracers.sfc)
if cmp -s build/decomp/uniracers.sfc "$ROM"; then
  echo "OK: build/decomp/uniracers.sfc matches $(sha1sum "$ROM" | cut -c1-40)"
else
  echo "MISMATCH: $(cmp -l build/decomp/uniracers.sfc "$ROM" | wc -l) bytes differ" >&2; exit 1
fi
