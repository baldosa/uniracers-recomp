# Uniracers SNES decomp — design

Target: the same ROM as the recomp (`Uniracers (USA).sfc`, SHA-1
`cb249cf7301bdd985e6fe4bc4c942bf4f86d7d83`). The ROM, its bytes and anything
generated from it never enter git.

## What "matching decomp" means for this game

Uniracers was written in hand-coded 65816 assembly: there is no compiler to
match, so the GBA skill's C-matching phase has no SNES counterpart. The
equivalent deliverable is a **matching disassembly**: Asar source that
rebuilds the ROM byte for byte, with every code byte as instructions, every
function named and commented, RAM and I/O symbolic, split by subsystem. The
recomp's generated C is the "decompiled C" view of the same program.

## Decisions

- **Generated listing, committed knowledge.** The `.asm` is regenerated from
  the decode and the owner's ROM at build time (`tools/decomp/build.sh`), so
  no ROM-derived bytes are committed. What is committed is everything a human
  adds: `decomp/symbols.txt` (function and label names and comments),
  `decomp/ram.txt` (RAM variables), `decomp/hw.asm` (I/O names) and
  `tools/decomp/code_hints.txt` (code that no static pass can prove). This
  keeps names and the instruction stream from drifting apart, the failure
  mode of hand-edited disassemblies.
- **The recomp's decode is the instruction authority.** `decode_dump.py`
  observes every instruction the recompiler compiles, with its M/X widths,
  and only fills gaps beyond it (off-route and dead code). Asar gets explicit
  operand sizes everywhere, so width mistakes cannot silently re-encode.
- **Names flow decomp → recomp.** `recomp/symbols.toml` names are exported
  from `decomp/symbols.txt`, so the generated C uses the same names.

## Code recovery (tools/decomp/decode_dump.py)

1. *Compiled set*: every instruction emitted by `v2_emit` (run in-process with
   one worker, so the observer sees every decode).
2. *Static closure*: LLE-only manifest variants, cfg dispatch targets and
   every static call/jump target outside the compiled set, decoded at the
   caller's widths with callee exit widths from the manifest or computed on
   demand.
3. *Dead code*: routines in the code banks' gaps, accepted only as a whole
   call tree whose decode is clean and closed (no BRK/COP/WDM/STP/WAI, no
   overlap, calls land on known starts), with evidence (I/O access, a call or
   join into known code, an undeclared jump table in known code, or being
   wedged between known code). Data filters: the game's text (lowercase with
   `_`), fill and value-table runs, word pointer tables, exotic opcodes, and
   bytes known code reads as data, rerun to a fixpoint as recovered code
   reveals more tables. Every acceptance is logged with its evidence in
   `build/decomp/dead.json` for review.

## Definition of done

1. `tools/decomp/build.sh` rebuilds the ROM byte-identically (gates commits).
2. Every code byte in banks $80-$83 is source; the remaining gaps are data
   (text, tables, graphics, music), each confirmed by a filter or by reading.
3. Every function named and commented; RAM variables named; I/O symbolic.
4. Subsystem files instead of per-bank files.
5. `recomp/symbols.toml` names generated from the decomp, recomp routes still
   matching.
6. Progress (`tools/decomp/progress.py`) reported in PROGRESS.md and CI.

## Not done here

C reconstruction of the assembly (no compiler to match; the recomp's C
already exists), and asset extraction (graphics/music stay incbin from the
owner's ROM).
