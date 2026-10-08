#!/usr/bin/env bash
# Build the web player (Emscripten: the recompiled game, no assets; the
# visitor loads their own ROM) and assemble the static site.
# usage: tools/web/build.sh [SITE_DIR]   (default: dist/web; needs emcmake on PATH)
#        INTERP=1 tools/web/build.sh     builds the interpreter host instead
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SITE="${1:-$ROOT/dist/web}"
cd "$ROOT"
emcmake cmake -S . -B build-web -G Ninja -DCMAKE_BUILD_TYPE=Release -DSNESRECOMP_INTERP_HOST=$([[ ${INTERP:-0} == 1 ]] && echo ON || echo OFF)
cmake --build build-web --target UniracersSNESRecomp
rm -rf "$SITE"; mkdir -p "$SITE"
cp web/index.html web/netplay.js web/settings.js build-web/uniracers.js build-web/uniracers.wasm "$SITE/"
touch "$SITE/.nojekyll"
ls -la "$SITE"
