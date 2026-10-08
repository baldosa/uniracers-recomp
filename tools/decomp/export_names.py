"""Export decomp names into the recomp, so the generated C reads the same.

usage: export_names.py

The decomp is the naming authority:
- every recomp [[func]] in recomp/symbols.toml still called sub_*/bank_*
  whose ROM address has a name in decomp/symbols.txt is renamed to it
  (continuation roots inside a function become Function_AAAA);
- functions the analyzer discovered on its own (no [[func]]) get a
  `symbol` line in their bank cfg: a naming-only overlay that never adds a
  root, so the generated code is unchanged except for its names. They are
  read from src/gen/program_manifest.json, so the order is regen, this,
  regen. A routine reached through the FastROM mirror ($80-$83 for
  $00-$03) is a separate C function: the twin that comes second is named
  Function_FastRom (or _SlowRom). Code copied to WRAM takes its ram.txt
  name.
"""
import bisect, json, pathlib, re, sys, tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'decomp'))
from gen_disasm import load_ram, load_symbols, to_offset

TOML = ROOT / 'recomp' / 'symbols.toml'
MANIFEST = ROOT / 'src' / 'gen' / 'program_manifest.json'
BEGIN = '# >>> BEGIN decomp symbols (tools/decomp/export_names.py — do not edit)'
END = '# <<< END decomp symbols'


def namer():
    names = {off: name for off, (name, _) in load_symbols().items() if off is not None}
    starts = sorted(names)
    ram = {addr & 0xFFFF: name for addr, _, name in load_ram()[0] if addr >> 16 == 0x7E}

    def name(pc24):
        if pc24 >> 16 in (0x00, 0x7E) and (pc24 & 0xFFFF) in ram:
            return 'Ram_' + re.sub(r'^w', '', ram[pc24 & 0xFFFF])
        off = to_offset(pc24)
        if off is None:
            return None
        if off in names:
            return names[off]
        # A continuation root inside a named function: Function_AAAA.
        i = bisect.bisect_right(starts, off) - 1
        if i >= 0 and starts[i] // 0x8000 == off // 0x8000:
            return f'{names[starts[i]]}_{pc24 & 0xFFFF:04X}'
        return None
    return name


def main():
    name = namer()
    text = TOML.read_text()
    funcs = tomllib.loads(text)['func']
    taken = {f['name'] for f in funcs}
    renamed = 0
    for f in funcs:
        new = name(f['bank'] << 16 | int(f['addr'], 16))
        if not new or not re.match(r'(sub|bank)_', f['name']) or new in taken:
            continue
        text, n = re.subn(rf'^name = "{re.escape(f["name"])}"$', f'name = "{new}"', text, flags=re.M)
        if n == 1:
            taken.add(new)
            renamed += 1
    TOML.write_text(text)
    print(f'renamed {renamed} recomp functions')

    funcs = tomllib.loads(text)['func']
    named = {f['bank'] << 16 | int(f['addr'], 16) for f in funcs}
    taken = {f['name'] for f in funcs}
    nodes = sorted({int(k.split(':')[0], 16) for k in json.loads(MANIFEST.read_text())['nodes']})
    by_bank, unnamed = {}, []
    for pc in nodes:
        if pc in named:
            continue
        new = name(pc)
        if new in taken:
            new += '_FastRom' if pc & 0x800000 else '_SlowRom'
        if not new or new in taken:
            unnamed.append(f'{pc:06X}')
            continue
        taken.add(new)
        by_bank.setdefault(pc >> 16, []).append(f'symbol {pc:06x} {new}')
    for cfg in sorted((ROOT / 'recomp').glob('bank*.cfg')):
        bank = int(cfg.stem[4:], 16)
        body = cfg.read_text()
        body = re.sub(rf'\n?{re.escape(BEGIN)}\n.*?{re.escape(END)}\n', '', body, flags=re.S)
        lines = by_bank.pop(bank, [])
        if lines:
            body = body.rstrip('\n') + f'\n\n{BEGIN}\n' + '\n'.join(lines) + f'\n{END}\n'
        cfg.write_text(body)
    for bank, lines in by_bank.items():
        unnamed += [l.split()[1] for l in lines]
    print(f'named {len(nodes) - len(named & set(nodes)) - len(unnamed)} discovered functions;'
          f' still unnamed: {" ".join(unnamed) or "none"}')


if __name__ == '__main__':
    main()
