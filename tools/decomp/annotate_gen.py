"""Put the decomp's description above each function in src/gen/*.c.

usage: annotate_gen.py   (tools/regen.sh runs it after generating)

The recompiler emits names but no comments; decomp/symbols.txt has a
one-line description for every routine. This writes it as a C comment
above each definition, including the per-CPU-state copies (_M1X0),
entry points inside a routine (Name_AAAA), ROM-mirror twins (_FastRom)
and code run from WRAM. Idempotent: comments it wrote before are replaced.
"""
import os, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'decomp'))
from gen_disasm import load_ram, load_symbols

TAG = '/* decomp: '
DEF = re.compile(r'^(?:RecompReturn|void) ([A-Za-z_][A-Za-z0-9_]*)\(CpuState \*cpu\) \{$')
MODE = {'M0X0': '16-bit A, 16-bit X/Y', 'M0X1': '16-bit A, 8-bit X/Y',
        'M1X0': '8-bit A, 16-bit X/Y', 'M1X1': '8-bit A, 8-bit X/Y'}


def describer():
    desc = {name: comment for name, comment in load_symbols().values()}
    ram = {'Ram_' + re.sub(r'^w', '', n): f'code the game copies to WRAM ${a & 0xFFFF:04X} and runs there'
           for a, _, n in load_ram()[0]}

    def describe(fn):
        m = re.fullmatch(r'(.+?)(?:_(M[01]X[01]))?', fn)
        name, mode = m.group(1), m.group(2)
        parts = []
        if name in ram:
            parts.append(ram[name])
        else:
            base, mirror = re.subn(r'_(FastRom|SlowRom)$', '', name)
            inner = re.fullmatch(r'(.+)_([0-9A-F]{4})', base)
            if base in desc:
                parts.append(desc[base] or base)
            elif inner and inner.group(1) in desc:
                parts.append(f'entry point at ${inner.group(2)} inside {inner.group(1)}: '
                             f'{desc[inner.group(1)]}')
            else:
                return None
            if mirror:
                parts.append('reached through the other ROM mirror bank')
        if mode:
            parts.append(f'compiled for {MODE[mode]}')
        return '; '.join(parts).replace('*/', '* /')
    return describe


def main():
    describe = describer()
    n = 0
    for path in sorted((ROOT / 'src' / 'gen').glob('*.c')):
        out, changed = [], False
        lines = path.read_text().split('\n')
        for i, line in enumerate(lines):
            if line.startswith(TAG) and i + 1 < len(lines) and DEF.match(lines[i + 1]):
                changed = True
                continue  # rewritten below
            m = DEF.match(line)
            if m and (d := describe(m.group(1))):
                out.append(f'{TAG}{d} */')
                changed = True
                n += 1
            out.append(line)
        if changed:
            # Replace, never modify in place: the generator hard-links
            # unchanged files between runs.
            tmp = path.with_suffix('.c.tmp')
            tmp.write_text('\n'.join(out))
            os.replace(tmp, path)
    print(f'annotate_gen: described {n} function definitions')


if __name__ == '__main__':
    main()
