# Uniracers SNES recomp + decomp — design

Target: `Uniracers (USA).sfc`, LoROM, no coprocessor, 2 MiB, 8 KiB SRAM,
SHA-1 `cb249cf7301bdd985e6fe4bc4c942bf4f86d7d83`. The ROM and anything derived
from it (`src/gen/`, dumps) never enter git.

## Decisions (agreed with the user)

- One repo (`uniracers-recomp`), built on snesrecomp (pinned submodule).
- Recomp first; the matching disassembly later lives in this repo and becomes
  the single source of truth for names and function boundaries
  (`symbols.toml` is generated from it).
- Goal is 100% on both: no middle-ground milestone.

## Definition of done

**Recomp**
1. Every executed 65816 instruction on the covered routes runs as AOT code:
   interpreter share of guest cycles = 0 and zero dispatch misses, with the
   interpreter kept only as the framework's safety net.
2. Routes covered: boot/attract, every main-menu branch, 1P race and stunt
   modes, 2P split-screen, VS, League progression, options, SRAM save/load.
3. Determinism: identical input script gives identical per-frame WRAM.
4. Equivalence: on every route script the AOT build, the interpreter-only
   build and snes9x (snesref) reach every `until` gate, and their `dump`
   checkpoints (WRAM + SRAM) match outside tools/state_mask.txt.

   Per-frame WRAM equality across tiers is NOT a goal: the AOT tier charges
   cycles per block (code-region speed) while the interpreter charges per bus
   transfer, so frames are cut a few cycles apart. Uniracers snapshots
   in-progress work at timing-dependent points (race-setup table $0764,
   palette-cycle counters), so only those bytes differ; each masked byte was
   traced to its writer. Exact tier parity (paced data accesses +
   per-instruction deadline checks in codegen) is a framework follow-up.

**Decomp** (separate spec when we get there): byte-identical matching
disassembly, 100% labelled, split per subsystem, named and commented; progress
on decomp.dev.

## Architecture

```
ROM ──► snesrecomp analyzer (recomp/*.cfg, symbols.toml, coverage profiles)
          └─► src/gen/*.c ──► + runner + src/game_rtl.c ──► native binary
route scripts (tests/routes/*.txt, host --script grammar)
          ├─► recomp binary  ──► per-frame WRAM dumps
          ├─► interp baseline ──┘   (tools/firstdiff.py → first divergence)
          └─► snesref (snes9x) ──► WRAM trace
```

Units:
- `recomp/` — analyzer config: roots, `indirect_dispatch` tables, boundaries.
  Only place codegen is steered. Never edit `src/gen/`.
- `tests/routes/` — input scripts, one per route; the shared contract for
  every comparison.
- `tools/` — small project scripts: headless runner, frame first-diff,
  contact sheet, coverage loop driver.
- `src/game_rtl.c` — frame model / interrupts, only if the framework's beam
  driver proves insufficient.

## Coverage loop (the main work)

1. Run all routes with coverage capture on.
2. Feed captures to `v2_emit --profile-manifest` (keeping historical ones),
   resolve each reported dispatch miss with an `indirect_dispatch` entry.
3. Regen, rebuild, rerun routes; first-diff vs baseline must be clean.
4. Repeat until interpreter share is 0.

## Error handling / risks

- Non-determinism found on day one (`$7E:00CE` at attract race start, stack
  byte at frame 402). Must be root-caused first: without determinism no
  comparison is meaningful.
- Framework bugs get fixed in the submodule (on a branch), not worked around
  in generated code.
- Headless host: SDL3 built with `SDL_UNIX_CONSOLE_BUILD`; GL headers from a
  user-local sysroot (`~/.local/sysroot`).
