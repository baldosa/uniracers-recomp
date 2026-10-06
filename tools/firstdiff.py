"""First frame where two route runs' WRAM differ.

usage: firstdiff.py RUN_A RUN_B   (exit 1 on a difference)
Each argument is a framedump dir holding crc.txt (one WRAM CRC per frame,
written by run_route.sh) or raw frame_NNNNNN_wram.bin files. With raw dumps
on both sides the differing offsets are reported too.
"""
import os, sys

def _crcs(d):
    p = f'{d}/crc.txt'
    return open(p).read().split() if os.path.exists(p) else None

def first_diff(a, b):
    raw = all(os.path.exists(f'{d}/frame_000000_wram.bin') for d in (a, b))
    ca, cb = _crcs(a), _crcs(b)
    if not raw and ca is not None and cb is not None:
        for f, (x, y) in enumerate(zip(ca, cb)):
            if x != y:
                return f, None
        return None
    f = 0
    while True:
        pa, pb = (f'{d}/frame_{f:06d}_wram.bin' for d in (a, b))
        if not (os.path.exists(pa) and os.path.exists(pb)):
            return None
        x, y = open(pa, 'rb').read(), open(pb, 'rb').read()
        if x != y:
            return f, [i for i in range(len(x)) if x[i] != y[i]]
        f += 1

if __name__ == '__main__':
    r = first_diff(*sys.argv[1:3])
    if r is None:
        print('identical'); sys.exit(0)
    f, offs = r
    if offs is None:
        print(f'frame {f}: WRAM CRC differs (re-run both with KEEP_WRAM=1 for offsets)')
    else:
        a, b = (open(f'{d}/frame_{f:06d}_wram.bin', 'rb').read() for d in sys.argv[1:3])
        print(f'frame {f}: {len(offs)} bytes:', ' '.join(f'{i:05X}:{a[i]:02X}/{b[i]:02X}' for i in offs[:24]))
    sys.exit(1)
