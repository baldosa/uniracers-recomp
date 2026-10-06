"""Timing-tolerant comparison of two runs: the sequence of distinct game states.

AOT code, the interpreter tier and other emulators charge CPU cycles
differently, so the same logical state lands on different host frames. A
trace keeps only the frames where masked WRAM changes, and two runs are
equivalent when their traces agree in order.

usage:
  statetrace.py write DUMPDIR [MASK]        -> DUMPDIR/trace.txt from raw WRAM dumps
  statetrace.py diff RUN_A RUN_B [MASK]     -> first divergent state (exit 1)
MASK is a file of hex WRAM offsets/ranges to ignore ("0100-01FF", "0012");
default tools/state_mask.txt.
"""
import hashlib, os, sys

DEFAULT_MASK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state_mask.txt')

def parse_mask(text):
    out = []
    for line in text.splitlines():
        line = line.split('#')[0].strip()
        if not line:
            continue
        lo, _, hi = line.partition('-')
        out.append((int(lo, 16), int(hi or lo, 16)))
    return out

def load_mask(path=DEFAULT_MASK):
    return parse_mask(open(path).read()) if os.path.exists(path) else []

def masked(data, mask):
    b = bytearray(data)
    for lo, hi in mask:
        b[lo:hi + 1] = bytes(len(b[lo:hi + 1]))
    return bytes(b)

def trace(dump_dir, mask):
    """[(frame, digest)] for every frame whose masked WRAM differs from the previous one."""
    out, prev, f = [], None, 0
    while True:
        p = f'{dump_dir}/frame_{f:06d}_wram.bin'
        if not os.path.exists(p):
            return out
        h = hashlib.blake2b(masked(open(p, 'rb').read(), mask), digest_size=12).hexdigest()
        if h != prev:
            out.append((f, h)); prev = h
        f += 1

def read_trace(path):
    return [(int(f), h) for f, h in (l.split() for l in open(path))]

def compare(ta, tb, window=64):
    """None if the traces agree, else (index_in_a, frame_a, frame_b) of the
    first mismatch that never resyncs.

    A frame boundary that cuts multi-frame work snapshots an in-between state
    on one side only, so on a mismatch the nearest common state within
    `window` steps on both sides is taken as the resync point. Near the end
    of a trace (routes finish idle) runs agree if their final states match.
    """
    i = j = 0
    while i < len(ta) and j < len(tb):
        if ta[i][1] == tb[j][1]:
            i += 1; j += 1
            continue
        ahead = [(di + dj, di, dj)
                 for di in range(window) for dj in range(window)
                 if i + di < len(ta) and j + dj < len(tb) and ta[i + di][1] == tb[j + dj][1]]
        if ahead:
            _, di, dj = min(ahead)
            i += di; j += dj
            continue
        if (i + window >= len(ta) or j + window >= len(tb)) and ta[-1][1] == tb[-1][1]:
            return None  # near the end and both settle in the same final state
        return i, ta[i][0], tb[j][0]
    return None

def _load(run):
    t = f'{run}/trace.txt'
    return read_trace(t) if os.path.exists(t) else trace(run, load_mask())

if __name__ == '__main__':
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == 'write':
        m = load_mask(args[1]) if len(args) > 1 else load_mask()
        t = trace(args[0], m)
        open(f'{args[0]}/trace.txt', 'w').write(''.join(f'{f} {h}\n' for f, h in t))
        print(f'{len(t)} distinct states')
    elif cmd == 'diff':
        ta, tb = _load(args[0]), _load(args[1])
        r = compare(ta, tb)
        if r is None:
            print(f'equivalent over {min(len(ta), len(tb))} states ({len(ta)} vs {len(tb)})'); sys.exit(0)
        i, fa, fb = r
        print(f'state #{i} differs: frame {fa} vs frame {fb}'); sys.exit(1)
