# Uniracers Recomp

A native recompilation of **Uniracers** (USA), built on
[snesrecomp](https://github.com/RetroPortingToolKit/snesrecomp).

Native static recompilation of Uniracers (SNES)



> **You must legally own a copy of the game.** No game assets are included,
> in the repository or in any release: graphics, music and tracks are read
> from your own ROM at runtime. The recompiled program logic (`src/gen/`) is
> committed; [src/gen/README.md](src/gen/README.md) explains what it is.
> Unofficial fan project, not affiliated with Nintendo or DMA Design.

## Status

**Recomp: the game runs as compiled native code.** On every scripted route
(boot/attract, 1P races on Dragster and Zoom Zoo, 2P split-screen, VS,
League, Options/Define/Records) the only instructions left to the
interpreter are the 7-instruction reset prologue that runs in 6502
emulation mode before `XCE` (the AOT tier compiles native-mode code only).

Every route checkpoint (WRAM + SRAM, `dump` in `tests/routes/*.txt`) matches
both the interpreter-only build and snes9x (snesref); masked bytes in
`tools/state_mask.txt` are each traced to a timing-phase writer.

**Decomp: a matching, fully named disassembly.** `tools/decomp/build.sh`
regenerates Asar source from your ROM and rebuilds it byte-identically.
All code in banks $80-$83 is source (42.8k instructions, including
off-route and unreferenced routines); everything else is data, incbin'd.
All 674 functions are named and commented, 620 RAM variables named, I/O
registers symbolic, and the source is split into 20 subsystem files. The
recomp's `symbols.toml` names are generated from it, so the generated C
reads the same.

See `docs/superpowers/` for the designs and plan.

Framework changes this port relies on (submodule branch, not yet upstream):
HVBJOY beam sync, native entry hand-off, `[[variant]]` roots,
`--historical-profile-manifest` passthrough, `paced_bus` codegen mode.

## Play

- **In the browser:** https://baldosa.github.io/uniracers-recomp/ — pick your
  own ROM; it never leaves your machine (the page can remember it in the
  browser). **Settings** rebinds keyboard and gamepad per player (two players
  on one keyboard included), picks the screen shape, size, smoothing and
  sound, and downloads or imports your battery save. Online two-player:
  *Create online game* shows a code, the friend *Join*s with it.
- **Downloads** (Linux x64, Linux arm64 / Raspberry Pi, Windows x64): the
  [Releases](https://github.com/baldosa/uniracers-recomp/releases) page, or
  the latest *Builds* workflow run's artifacts.

Both are the full recomp, built from the committed `src/gen/` (5× the
interpreter's speed in the browser). Neither contains any game data: you
load your own ROM. `-DSNESRECOMP_INTERP_HOST=ON` (or `INTERP=1
tools/web/build.sh`) builds the plain interpreter instead.

## ROM identity

| | |
|---|---|
| File | `Uniracers (USA).sfc` |
| Publisher | Nintendo / DMA Design |
| Developer | — |
| Year | 1994 |
| Mapping | lorom |
| Region | USA (North America) |
| Coprocessor | none |
| CRC32 | `383858c7` |
| SHA-256 | `859ec99fdc25dd9b239d9085bf656e4f49c93a32faa5bb248da83efd68ebd478` |

`tools/regen.sh` refuses to run against anything else, so a mismatched
revision fails immediately instead of producing subtly wrong output.

## Build

```sh
git submodule update --init --recursive
bash tools/regen.sh --rom /path/to/Uniracers (USA).sfc
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
```

The ROM does not have to live in the repository — keeping it on your own
drive is the better habit, and `SNESRECOMP_ROM` sets the path once for a
shell. Without either, `tools/regen.sh` finds `Uniracers (USA).sfc` at the repo root,
then the path the setup wizard recorded in `rom.cfg`; `.gitignore` blocks
both from ever being committed.

`tools/regen.sh` verifies the ROM, generates `src/gen/*.c`, and re-syncs
`recomp/funcs.h`. Re-run it whenever you change anything under `recomp/`.

### Raspberry Pi (arm64)

Use 64-bit Raspberry Pi OS. Build on the Pi, but generate the C on a PC: the
generated code is architecture-independent, so the Pi never needs Rust or
the analyzer.

```sh
# on the PC, after tools/regen.sh: copy the repo, src/gen/ included
rsync -a --exclude build/ uniracers-recomp/ pi@raspberrypi:uniracers-recomp/

# on the Pi
sudo apt install build-essential cmake ninja-build pkg-config \
  libx11-dev libxext-dev libxrandr-dev libxcursor-dev libxi-dev libxss-dev \
  libwayland-dev libxkbcommon-dev libegl-dev libgles-dev libgl-dev \
  libdrm-dev libgbm-dev libasound2-dev libpulse-dev libudev-dev
cd uniracers-recomp
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2        # -j2: the generated files need RAM; add swap on 1-2 GB Pis
./build/UniracersSNESRecomp ~/uni.sfc
```

The default presenter goes through SDL's renderer (GLES on the Pi), so it
also runs on a Pi 3; the OpenGL presenter needs GL 3.1 (Pi 4/5). With
`libdrm-dev`/`libgbm-dev` installed SDL can also run straight on the console
(KMSDRM), without a desktop.

The arm64 build is checked on x86 under qemu: `tools/cross/aarch64-linux.cmake`
cross-compiles with Zig (static musl), and `BIN=tools/cross/run-arm64.sh
tools/routes.sh OUT baselines/snes9x` runs every route; all checkpoints match.

### Decomp

```sh
tools/decomp/build.sh /path/to/Uniracers (USA).sfc   # needs asar (1.91) on PATH
```

Decodes the program (through the recompiler), writes the Asar source to
`build/disasm/` (one file per subsystem), assembles it and checks the result
is byte-identical to the ROM. The source is generated from your ROM, never
committed; what is committed is the knowledge in `decomp/`.
`tools/decomp/progress.py` reports coverage and naming.

## Run

```sh
./build/UniracersSNESRecomp                     # launcher picks the ROM
./build/UniracersSNESRecomp /path/to/Uniracers (USA).sfc # or name it and skip the launcher
```

With no ROM on the command line the build opens the recomp-ui launcher: a ROM
picker with a verification badge, plus display / audio / input settings. Your
choice is cached in `rom.cfg` beside the executable, so the next launch opens
on it and "Skip launcher on boot" makes it immediate. If the launcher is not
built in (`--no-recomp-ui`), the host falls back to a native file picker.

Either way the ROM is checked against the digests above before anything boots
— a dump that could not have produced this build is refused at the door rather
than mis-executing ten frames in.

### Controls and settings

The launcher ([recomp-ui](https://github.com/RetroPortingToolKit/recomp-ui))
sets everything: per-player keyboard or gamepad bindings, window scale,
renderer, fullscreen, filtering, vsync, run-ahead, audio, hotkeys and mods.
**Ctrl+L** (or Select+L3 on a gamepad) reopens it mid-game; most changes
apply on Resume. Settings live in `config.ini` and `keybinds.ini` beside
the executable, which you can also edit by hand (`[player1]` / `[player2]`
map `a b x y l r start select up down left right` to SDL key names).

## Layout

| Path | What lives there |
|---|---|
| `recomp/` | Analysis input: `bank*.cfg`, `symbols.toml`, generated `funcs.h` |
| `rom_identity.txt` | ROM digests — read by the build, `tools/regen.sh` and CI |
| `src/` | Host code you own: `main.c`, `game_rtl.c` |
| `src/gen/` | Generated C (machine-translated game logic, no assets): `tools/regen.sh` rebuilds it |
| `snesrecomp/` | Framework submodule (owns `lib/recomp-net`, `lib/retcomm-rbengine`) |
| `tools/` | `regen.sh` — the ROM → C pipeline |
| `decomp/` | Decomp knowledge: `symbols.txt` (names, comments), `ram.txt`, `hw.asm`, `subsystems.txt` |
| `tools/decomp/` | `build.sh` — decode, generate the Asar disassembly, rebuild, compare |
| `scripts/` | `package_release.sh` — player-facing zip |
| `framework_pins.txt` | Exact framework commits this project was scaffolded against |

## Porting from here

The scaffold stops where the game-specific work starts. In rough order:

1. **Make it boot.** `src/game_rtl.c` holds the frame driver. It starts on
   the framework's beam-aligned driver (`snesrecomp/runner/src/beam_frame_driver.h`):
   one frame per PPU field, interrupts taken where the beam latches them,
   the field rasterized from the raster journal. A title whose main loop it
   does not fit replaces those calls with its own driver.
2. **Name things.** Add entries to `recomp/symbols.toml` as you identify
   routines, then re-run `tools/regen.sh`. Set `emit = true` to promote one
   into ahead-of-time analysis; leave it false to keep it interpreted.
   Regen synchronizes the marked blocks in each bank cfg, creating missing
   configs. Only proven variants become AOT code. See `recomp/README.md`.
3. **Resolve dispatch misses.** After every run, deal with unresolved
   indirect targets before anything else — they are the reason a port
   diverges, and they are cheap to fix early.
4. **Never synthesise a result** to get past uncovered code, and never edit
   `src/gen/` by hand. Fix the config or the framework and regenerate.

## Multiplayer

Two players, one controller per port.

## License

This project's own source is under the license in `LICENSE`. The framework
carries its own terms — see `snesrecomp/LICENSE` and
`snesrecomp/THIRD_PARTY_ATTRIBUTION.md`. Neither covers the game data, which
is not distributed here.
