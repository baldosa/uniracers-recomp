"""Self-check for the disassembly generator and the dead-code data filters."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, '..', '..', 'snesrecomp', 'tools'),
                os.path.join(HERE, '..', '..', 'snesrecomp', 'recompiler')]
from gen_disasm import fmt, insn_length, snes, target, to_offset
from decode_dump import TEXT

# Operand sizes are explicit so Asar reproduces the original encoding.
assert fmt(bytes([0xA9, 0x34, 0x12]), 0, 0, None) == 'lda.w #$1234'
assert fmt(bytes([0xA9, 0x34]), 1, 0, None) == 'lda.b #$34'
assert fmt(bytes([0xAD, 0x00, 0x21]), 1, 1, None) == 'lda.w $2100'
assert fmt(bytes([0xAF, 0x48, 0x07, 0x77]), 1, 1, None) == 'lda.l $770748'
assert fmt(bytes([0x54, 0x7E, 0x80]), 1, 1, None) == 'mvn $7E,$80'   # machine byte order
assert fmt(bytes([0xD0, 0xFB]), 1, 1, 'CODE_80B71A') == 'bne CODE_80B71A'
assert insn_length(0xA2, 1, 0) == 3 and insn_length(0xA2, 1, 1) == 2
# LoROM mapping in the FastROM mirror, and relative targets.
assert snes(0x1AB9A) == 0x83AB9A and to_offset(0x03AB9A) == to_offset(0x83AB9A) == 0x1AB9A
assert to_offset(0x7E2000) is None and to_offset(0x800199) is None
assert target(0xB71D, bytes([0x30, 0xFB]), 'rel') == 0x81B71A  # BMI back 5
# The game's strings are lowercase with '_' for spaces; code is not.
assert TEXT.search(b'\xa9racing_on\x60') and not TEXT.search(bytes([0x4A] * 6 + [0x60]))
print('ok')
