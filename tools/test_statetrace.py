import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from statetrace import trace, compare, parse_mask

def dump(d, frames):
    os.makedirs(d)
    for f, data in enumerate(frames):
        open(f'{d}/frame_{f:06d}_wram.bin', 'wb').write(bytes(data))

def st(*vals, stack=0):
    b = bytearray(0x300); b[0x10:0x10 + len(vals)] = bytes(vals); b[0x1F0] = stack
    return b

mask = parse_mask('0100-01FF\n# comment\n0012\n')
assert mask == [(0x100, 0x1FF), (0x12, 0x12)]

with tempfile.TemporaryDirectory() as t:
    # a: states A A B C ; b: A B B B C (slower, same logical sequence), stack noise
    dump(f'{t}/a', [st(1), st(1), st(2), st(3)])
    dump(f'{t}/b', [st(1, stack=9), st(2), st(2, stack=4), st(2), st(3)])
    ta, tb = trace(f'{t}/a', mask), trace(f'{t}/b', mask)
    assert [f for f, _ in ta] == [0, 2, 3] and [f for f, _ in tb] == [0, 1, 4]
    assert compare(ta, tb) is None
    # masked single byte ($12) is ignored too
    dump(f'{t}/c', [st(1), st(2, 0, 7), st(3)])
    assert compare(ta, trace(f'{t}/c', mask)) is None
    # in-between states from a frame cut mid-work resync: A B C vs A X B Y C
    dump(f'{t}/m', [st(1), st(9), st(2), st(8), st(3)])
    assert compare(ta, trace(f'{t}/m', mask)) is None
    # real divergence: never resyncs -> reported at first mismatch, frames (3, 2)
    dump(f'{t}/d', [st(1), st(2), st(4), st(5), st(6)])
    assert compare(ta, trace(f'{t}/d', mask)) == (2, 3, 2)
    # one side ends early: common prefix equal -> no divergence reported
    dump(f'{t}/e', [st(1), st(2)])
    assert compare(ta, trace(f'{t}/e', mask)) is None
print('ok')
