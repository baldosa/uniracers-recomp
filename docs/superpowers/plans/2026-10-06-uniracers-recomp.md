# Uniracers Recomp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uniracers running 100% as AOT-recompiled code, deterministic, and
equivalent to the interpreter and snes9x on every route.

**Architecture:** snesrecomp project (scaffolded). Work happens in `recomp/`
(analyzer config), `tests/routes/` (input scripts) and `tools/` (harness).
Framework fixes go to the `snesrecomp` submodule on a branch.

**Tech Stack:** snesrecomp (C runtime, Python + Rust analyzer), CMake/Ninja,
SDL3 (console build), Python 3.13 (stdlib; Pillow only for contact sheets).

Environment for every command:
```sh
. $HOME/.cargo/env; export PATH=$HOME/.local/bin:$PATH
export SNESRECOMP_ROM="/home/dev/uniracers-recomp/Uniracers (USA).sfc"
```

---

### Task 1: Harness tools in the repo

**Files:**
- Create: `tools/run_route.sh` — headless run of one script, framedump on
- Create: `tools/firstdiff.py` — first frame where two framedumps' WRAM differ
- Create: `tools/test_firstdiff.py` — assert-based check
- Create: `tests/routes/attract.txt` — `turbo on` / `wait 3000` / `quit`

- [ ] Step 1: write `tools/test_firstdiff.py` building two tiny fake dump dirs
  (identical, then one byte changed at frame 2) and asserting the result.
- [ ] Step 2: run it, expect ImportError/failure.
- [ ] Step 3: write `tools/firstdiff.py` exposing `first_diff(a, b) -> (frame, [offsets]) | None`
  plus a CLI (exit 1 on diff).
- [ ] Step 4: `python3 -I tools/test_firstdiff.py` passes.
- [ ] Step 5: `tools/run_route.sh tests/routes/attract.txt OUT` exits 0.
- [ ] Step 6: commit.

### Task 2: Root-cause the non-determinism

Known symptoms: `$7E:00CE` differs at frame 1411 (attract race start) in
every repeat run; `$7E:01F3` (stack) differs at frame 402 in some runs.

- [ ] Step 1: build a trace build (`build-trace`, `-DSNESRECOMP_ENABLE_TRACE=ON`),
  find the code writing `$CE` (debug server `trace addr`, or static scan of
  the ROM for `STA/INC $CE`).
- [ ] Step 2: identify the input to that code that differs between runs
  (hardware register read, APU port, wall-clock-paced work).
- [ ] Step 3: fix at the root in the framework (submodule branch
  `uniracers/determinism`) or in `src/game_rtl.c` if it is host policy.
- [ ] Step 4: exit criterion: 5 repeat runs of `attract.txt` with
  `tools/firstdiff.py` → identical through the last frame.
- [ ] Step 5: commit (and the submodule pointer).

### Task 3: Route scripts

**Files:** `tests/routes/{attract,menu_all,race_1p,stunt_1p,race_2p,vs,league,options_save}.txt`

- [ ] Step 1: for each route, write the script using the host grammar
  (`press`, `wait`, `until`, `quit`), verify by contact sheet that it reaches
  the intended screens.
- [ ] Step 2: record interpreter baselines: `tools/run_route.sh` per route into
  `baselines/` (gitignored; derived data), with per-frame WRAM.
- [ ] Step 3: commit scripts.

### Task 4: Coverage loop to 100% AOT

**Files:** `recomp/*.cfg`, `recomp/symbols.toml`, `tools/coverage_loop.sh`

- [ ] Step 1: `tools/coverage_loop.sh` runs every route with
  `SNESRECOMP_TIER2_CAPTURE=1`, keeps captures under `coverage/` (gitignored),
  runs `snesrecomp/tools/tier2_ingest.py`, regenerates with
  `--profile-manifest` for all captures, rebuilds.
- [ ] Step 2: iterate: resolve each dispatch miss with `indirect_dispatch`
  entries in `recomp/bankNN.cfg`; regen; rerun routes; `firstdiff` vs
  baseline must be clean for every route.
- [ ] Step 3: exit criterion: interpreter cycles = 0 on all routes, zero
  dispatch misses, every route first-diff clean.
- [ ] Step 4: commit after every iteration that stays clean.

### Task 5: External oracle (snes9x via snesref)

- [ ] Step 1: build `snesrecomp/tools/snesref` (SDL2 headers via user-local
  sysroot), fetch `snes9x_libretro.so`.
- [ ] Step 2: run every route script in snesref, diff WRAM traces against the
  recomp; document device-model differences that are not game bugs.
- [ ] Step 3: commit any tooling/docs.

### Task 6: Release hygiene

- [ ] Step 1: README status, controls, build instructions (headless and
  desktop), no ROM-derived data in the tree (`git ls-files` check).
- [ ] Step 2: commit.

## Status 2026-10-06 (end of session)

Done: scaffold, headless harness, deterministic routes (7), snes9x oracle
(snesref + pad-2 scripting), checkpoint oracle (interp == snes9x == AOT),
framework fix HVBJOY beam sync (branch uniracers/hvbjoy-beam-sync), coverage
loop tools (capture_coverage.sh, promote_roots.py), 164 promoted roots.

In progress (framework branch uniracers/native-handoff, game side OFF):
native entry hand-off so frame resumes / NMI run compiled. Remaining
interpreted work is ~68% the WaitForNMI spin resumed in the interpreter.
Blocker found: compiled I_NMI's `JML [$0053]` tiers down with subroutine
stack semantics and over-pops 3 bytes after the handler's RTI. Next step:
resolve it in cfg as an indirect dispatch with the only three handlers the
ROM installs: $80:F60C (80:A165), $80:8610 (82:D74D), $80:85A5 (82:DE1B);
then set I_NMI/I_RESET emit = true and enable the hand-off in game_rtl.c.
Then: promote resume/continuation PCs from captures, League route, decomp.

## Status 2026-10-07

Recomp milestone reached: all routes interpret only the 7-instruction
emulation-mode reset prologue; checkpoints match interpreter build and
snes9x. Coverage loop: `tools/coverage_iter.sh PREV NEXT` (promote ->
regen with every capture dir as seeds -> build -> capture + validate).
Remaining: League route; then the decomp spec (matching disassembly whose
labels feed recomp/symbols.toml).

## Status 2026-10-07 (later)

League route added (define a league in Options, race it 2P); three coverage
iterations (it34-it37) brought it to the 7-instruction floor. Reading the
disassembly exposed five analysis facts the recomp had wrong (two dispatch
tables with a text word as 4th target, and three PHP/PLP exit widths the
solver could not see: $C775, $951C, $8151, plus $879A); all fixed in cfg.
All eight routes x nine checkpoints match the interpreter build and snes9x.
Decomp done per docs/superpowers/specs/2026-10-07-uniracers-decomp-design.md:
byte-identical rebuild, 674/674 functions named and commented, 620 RAM
variables, 20 subsystem files, names exported to recomp/symbols.toml.
