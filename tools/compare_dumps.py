"""Compare `dump <tag>` checkpoints of two route runs (recomp or snesref).

usage: compare_dumps.py RUN_A RUN_B   (each holds dump/<tag>.wram.bin, .sram.bin)
Prints per tag the WRAM bytes that differ (stack and tools/state_mask.txt
masked) and whether SRAM matches, and OAM too when both sides dumped it
(the snesref core needs the debug patch for that). Exit 1 if any tag is missing on one side
or differs in more than ALLOW bytes (env, default 0).

Exact equality is not always reachable across execution tiers or emulators:
Uniracers snapshots work in progress at timing-dependent points (e.g. the
race-setup table at $0764), so a few bytes may legitimately differ.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from statetrace import load_mask, masked

def tags(run):
    d = f'{run}/dump'
    return sorted(f[:-9] for f in os.listdir(d) if f.endswith('.wram.bin')) if os.path.isdir(d) else []

# $83:9894 copies WRAM $0000-$019F into SRAM $0E6B-$100A, so masked
# direct-page/stack bytes reappear there.
SRAM_DP_MIRROR, DP_MIRROR_LEN = 0x0E6B, 0x1A0

def sram_mask(mask):
    return [(SRAM_DP_MIRROR + lo, SRAM_DP_MIRROR + min(hi, DP_MIRROR_LEN - 1))
            for lo, hi in mask if lo < DP_MIRROR_LEN]

def diff(a, b, mask):
    x, y = masked(a, mask), masked(b, mask)
    return [i for i in range(min(len(x), len(y))) if x[i] != y[i]]

def main(a, b, allow):
    mask = load_mask() + [(0x100, 0x1FF)]
    ok = True
    ta, tb = tags(a), tags(b)
    for t in sorted(set(ta) | set(tb)):
        if t not in ta or t not in tb:
            print(f'{t}: missing on {"A" if t not in ta else "B"}'); ok = False; continue
        rd = lambda r, ext: open(f'{r}/dump/{t}.{ext}.bin', 'rb').read()
        d = diff(rd(a, 'wram'), rd(b, 'wram'), mask)
        sram_same = not diff(rd(a, 'sram'), rd(b, 'sram'), sram_mask(mask))
        wa, wb = rd(a, 'wram'), rd(b, 'wram')
        print(f'{t}: wram {len(d)} bytes differ' + ('' if not d else ': ' + ' '.join(
            f'{i:05X}:{wa[i]:02X}/{wb[i]:02X}' for i in d[:16])) + f'; sram {"same" if sram_same else "DIFFERS"}')
        ok &= len(d) <= allow and sram_same
        if all(os.path.exists(f'{r}/dump/{t}.oam.bin') for r in (a, b)):
            oa, ob = rd(a, 'oam'), rd(b, 'oam')
            od = [i for i in range(len(oa)) if oa[i] != ob[i]]
            print(f'{t}: oam {len(od)} bytes differ' + ''.join(f' {i:03X}:{oa[i]:02X}/{ob[i]:02X}' for i in od[:16]))
            ok &= not od
    return ok

if __name__ == '__main__':
    sys.exit(0 if main(sys.argv[1], sys.argv[2], int(os.environ.get('ALLOW', '0'))) else 1)
