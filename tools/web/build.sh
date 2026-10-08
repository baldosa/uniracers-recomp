#!/usr/bin/env bash
# Build the web player (Emscripten, interpreter host: no recompiled code, no
# ROM data) and assemble the static site.
# usage: tools/web/build.sh [SITE_DIR]   (default: dist/web; needs emcmake on PATH)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SITE="${1:-$ROOT/dist/web}"
cd "$ROOT"
emcmake cmake -S . -B build-web -G Ninja -DCMAKE_BUILD_TYPE=Release -DSNESRECOMP_INTERP_HOST=ON
cmake --build build-web --target UniracersSNESRecomp
rm -rf "$SITE"; mkdir -p "$SITE"
cp web/index.html web/netplay.js build-web/uniracers.js build-web/uniracers.wasm "$SITE/"
touch "$SITE/.nojekyll"
ls -la "$SITE"
