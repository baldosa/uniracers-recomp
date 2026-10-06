import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from firstdiff import first_diff

def dump(d, frames):
    os.makedirs(d)
    for f, data in enumerate(frames):
        open(f'{d}/frame_{f:06d}_wram.bin', 'wb').write(data)

with tempfile.TemporaryDirectory() as t:
    base = [bytes(16)] * 4
    dump(f'{t}/a', base)
    dump(f'{t}/b', base)
    assert first_diff(f'{t}/a', f'{t}/b') is None
    changed = list(base); changed[2] = bytes(5) + b'\x07' + bytes(10)
    dump(f'{t}/c', changed)
    assert first_diff(f'{t}/a', f'{t}/c') == (2, [5])
print('ok')
