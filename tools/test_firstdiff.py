import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from firstdiff import first_diff

def dump(d, frames):
    os.makedirs(d)
    for f, data in enumerate(frames):
        open(f'{d}/frame_{f:06d}_wram.bin', 'wb').write(data)

def crcs(d, lines):
    os.makedirs(d)
    open(f'{d}/crc.txt', 'w').write(''.join(f'{x}\n' for x in lines))

with tempfile.TemporaryDirectory() as t:
    base = [bytes(16)] * 4
    dump(f'{t}/a', base)
    dump(f'{t}/b', base)
    assert first_diff(f'{t}/a', f'{t}/b') is None
    changed = list(base); changed[2] = bytes(5) + b'\x07' + bytes(10)
    dump(f'{t}/c', changed)
    assert first_diff(f'{t}/a', f'{t}/c') == (2, [5])
    # crc.txt mode: offsets unknown, frame still exact; shorter run compares its prefix
    crcs(f'{t}/x', ['0x1', '0x2', '0x3'])
    crcs(f'{t}/y', ['0x1', '0x2', '0x3', '0x4'])
    crcs(f'{t}/z', ['0x1', '0x9', '0x3'])
    assert first_diff(f'{t}/x', f'{t}/y') is None
    assert first_diff(f'{t}/x', f'{t}/z') == (1, None)
print('ok')
