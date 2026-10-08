# src/gen — machine-generated C. Read this first.

**Everything in this folder except this README was written by a program,
not a person.** [snesrecomp](https://github.com/RetroPortingToolKit/snesrecomp)
read the 65816 machine code of *Uniracers* (SNES, 1994) and translated each
routine into C, mechanically, one instruction at a time. `recomp/funcs.h` is
generated the same way.

## What is (and isn't) here

- **Here:** the game's *program logic*, translated. A function like
  `bank_82_B8AB_M1X0` is the original routine at address `$82:B8AB`, compiled
  for the CPU state "8-bit accumulator, 16-bit index registers". The cycle
  counting, `cpu_write8_paced` calls and `interp_*` fallbacks are the
  recompiler's scaffolding, which keeps the timing identical to real hardware.
- **Not here:** any game assets. Graphics, music, sound, tracks and text
  stay in the ROM. The program reads them from *your* ROM file at runtime,
  and refuses any file whose SHA-256 is not the one in `rom_identity.txt`
  (the only byte array in these files is that hash). **The code here does
  nothing without your own copy of the game.**

## Reading the names

Every function carries the name the decomp gave the routine
(`decomp/symbols.txt`, where each one also has a one-line description):

| Name | Meaning |
|---|---|
| `Sram_ValidateOrInit` | `Subsystem_WhatItDoes`: the routine itself |
| `MainMenu_Draw_ACE8` | an entry point inside `MainMenu_Draw`, at `$ACE8` |
| `..._M1X0` | compiled for one CPU state: M=1 8-bit / 0 16-bit accumulator, X likewise for X/Y. A routine entered in several states has one copy per state |
| `..._FastRom` / `_SlowRom` | the same routine reached through the other ROM mirror ($80-$83 vs $00-$03), which the hardware times differently |
| `Ram_MvnTrampoline` | code the game copies into RAM and runs there |

## Don't edit these files

They are build output. Change `recomp/*.cfg` or `recomp/symbols.toml` and
regenerate:

```sh
bash tools/regen.sh --rom "/path/to/Uniracers (USA).sfc"
```

Regenerating from the same ROM and config reproduces these files exactly.
For a readable version of the same program, with names and comments, see the
decomp (`decomp/`, `tools/decomp/build.sh`).

## Legal

*Uniracers* © 1994 Nintendo / DMA Design. This is an unofficial,
non-commercial fan preservation project, and is not affiliated with or
endorsed by Nintendo or DMA Design (now Rockstar North). The translated
program logic in this folder derives from their copyrighted work. It is
published for study, preservation and interoperability, and it ships no
assets. You must own the game to play it. Rights holders who want this
removed can open an issue on the repository.
