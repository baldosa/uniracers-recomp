"""First frame where two framedump directories' WRAM differ.

usage: firstdiff.py DUMP_A DUMP_B   (exit 1 and print offsets on a difference)
"""
import os, sys

def first_diff(a, b):
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
    a, b = (open(f'{d}/frame_{f:06d}_wram.bin', 'rb').read() for d in sys.argv[1:3])
    print(f'frame {f}: {len(offs)} bytes:', ' '.join(f'{i:05X}:{a[i]:02X}/{b[i]:02X}' for i in offs[:24]))
    sys.exit(1)
