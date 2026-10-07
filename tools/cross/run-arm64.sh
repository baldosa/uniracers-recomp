#!/bin/sh
# Run the arm64 build under user-mode qemu (for tools/run_route.sh BIN=...).
exec qemu-aarch64 "$(dirname "$0")/../../build-arm64/UniracersSNESRecomp" "$@"
