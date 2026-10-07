/* Hand-written bodies for code the recompiler could not translate.
 *
 * Empty at scaffold time. Fill this in as regeneration reports unresolved
 * targets — and fill it in with real behaviour, never with a value invented
 * to get past the gap. An invented result turns a loud failure into a silent
 * wrong one (recomp-ai-rules/PRINCIPLES.md, "No stubs"). If a routine cannot
 * be translated yet, leave it to the interpreter tier instead.
 */

#include <stdio.h>
#include <stdlib.h>
#include "cpu_state.h"

/* $00:0199 is a RAM trampoline the game builds at init: MVN $00,$80 ; RTL
 * (bytes 54 00 80 6B). Callers ($80:9B2F, $80:9B55, ...) patch the source
 * bank into $019B and the destination bank into $019A, load A = count - 1,
 * X = source, Y = destination, then JSL $000199. The interpreter executes it
 * one MVN step per byte; this replacement performs the same block move and
 * the RTL (hle_func 0199 in bank00.cfg).
 *
 * MVN: repeat { [dst:Y] = [src:X]; X++; Y++; A-- } until A wraps to $FFFF,
 * leaving DB = destination bank; P is untouched. Index registers wrap at
 * their live width. Timing: 7 CPU cycles per byte (opcode and both operand
 * bytes re-fetched from WRAM each step, source read, destination write, two
 * internal cycles), then RTL (6 cycles: fetch, two internal, three stack
 * reads). */
RecompReturn HleRamBlockMove(CpuState *cpu)
{
    if (cpu->ram[0x199] != 0x54 || cpu->ram[0x19C] != 0x6B) {
        fprintf(stderr, "HleRamBlockMove: $0199 holds %02X %02X %02X %02X, not MVN/RTL\n",
                cpu->ram[0x199], cpu->ram[0x19A], cpu->ram[0x19B], cpu->ram[0x19C]);
        abort();
    }
    const uint8 dst_bank = cpu->ram[0x19A], src_bank = cpu->ram[0x19B];
    const uint16 index_mask = (cpu->x_flag & 1) ? 0x00FF : 0xFFFF;
    const uint32_t wram_code = cpu_region_speed(0x000199);
    do {
        const uint8 v = cpu_read8(cpu, src_bank, cpu->X);
        cpu_write8(cpu, dst_bank, cpu->Y, v);
        cpu->master_cycles += 3 * wram_code + 2 * 6 +
            cpu_region_speed(((uint32_t)src_bank << 16) | cpu->X) +
            cpu_region_speed(((uint32_t)dst_bank << 16) | cpu->Y);
        cpu->cycles += 7;
        cpu->X = (uint16)((cpu->X + 1) & index_mask);
        cpu->Y = (uint16)((cpu->Y + 1) & index_mask);
        cpu->A = (uint16)(cpu->A - 1);
    } while (cpu->A != 0xFFFF);
    cpu->DB = dst_bank;
    /* RTL: pop the 3-byte frame the caller's JSL pushed. */
    cpu->S = (uint16)(cpu->S + 3);
    cpu->cycles += 6;
    cpu->master_cycles += 4 * wram_code + 2 * 6;
    return RECOMP_RETURN_NORMAL;
}
