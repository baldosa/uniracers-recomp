"""Merge naming maps into decomp/symbols.txt and decomp/ram.txt.

usage: apply_names.py NAMES.json [...]

Each map is {"functions": [{"old": "sub_BBAAAA", "new": NAME, "comment": ...}],
"ram": [{"addr": "7E009B", "name": NAME, "size": N, "comment": ...}]}.
Names must be valid identifiers and unique across both files; an address
that already has a name keeps it. Rejections are printed, never applied.
Renames never change code, so tools/decomp/build.sh verifies the result.
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SYMBOLS = ROOT / 'decomp' / 'symbols.txt'
RAM = ROOT / 'decomp' / 'ram.txt'
IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def parse(path):
    """{addr24: (name, rest-of-line)} for a symbols-style file."""
    out = {}
    for line in path.read_text().splitlines() if path.exists() else ():
        body = line.partition(';')[0].split()
        if body and not line.lstrip().startswith('#'):
            out[int(body[0], 16)] = (body[1], line)
    return out


def ram_addr(text):
    a = int(text, 16)
    if (a >> 16) & 0x7F < 0x40 and (a & 0xFFFF) < 0x2000:
        a = 0x7E0000 | (a & 0xFFFF)  # low WRAM through a ROM-bank mirror
    return a


def one_line(text):
    return ' '.join(str(text or '').split())


def main(maps):
    syms, ram = parse(SYMBOLS), parse(RAM)
    taken = {n for n, _ in syms.values()} | {n for n, _ in ram.values()}
    new_syms, new_ram, rejected = [], [], []
    for path in maps:
        data = json.loads(pathlib.Path(path).read_text())
        for f in data.get('functions', []):
            m = re.fullmatch(r'sub_([0-9A-F]{6})', f.get('old', ''))
            name = f.get('new', '')
            if not m or not IDENT.match(name) or name in taken or int(m.group(1), 16) in syms:
                rejected.append(('func', f.get('old'), name))
                continue
            taken.add(name)
            syms[int(m.group(1), 16)] = (name, None)
            new_syms.append(f'{m.group(1)} {name:<26} ; {one_line(f.get("comment"))}'.rstrip(' ;'))
        for r in data.get('ram', []):
            name = r.get('name', '')
            try:
                a = ram_addr(r['addr'])
                size = int(r.get('size') or 1)
            except (KeyError, ValueError, TypeError):
                rejected.append(('ram', r.get('addr'), name))
                continue
            if not IDENT.match(name) or name in taken or a in ram or not (
                    (a >> 16) in (0x7E, 0x7F) or 0x70 <= (a >> 16) <= 0x77):
                rejected.append(('ram', r.get('addr'), name))
                continue
            taken.add(name)
            ram[a] = (name, None)
            new_ram.append((a, f'{a:06X} {name:<24} {size:<4} ; {one_line(r.get("comment"))}'.rstrip(' ;')))
    if new_syms:
        with SYMBOLS.open('a') as fh:
            fh.write('\n'.join(['# Proposed by the naming pass'] + sorted(new_syms)) + '\n')
    if new_ram or not RAM.exists():
        lines = [l for _, l in sorted((a, l) for a, (n, l) in ram.items() if l)]
        lines += [l for _, l in sorted(new_ram)]
        header = ['# RAM variables for the disassembly (tools/decomp/gen_disasm.py).',
                  '# BBAAAA name size ; comment   (WRAM $7E/$7F, SRAM $70-$77; D = $0000)']
        RAM.write_text('\n'.join(header + sorted(lines, key=lambda l: l[:6])) + '\n')
    print(f'applied {len(new_syms)} function names, {len(new_ram)} RAM names; '
          f'rejected {len(rejected)}')
    for r in rejected:
        print('  rejected', *r)


if __name__ == '__main__':
    main(sys.argv[1:])
