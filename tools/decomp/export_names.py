"""Export decomp names into recomp/symbols.toml.

usage: export_names.py

The decomp is the naming authority: every recomp [[func]] still called
sub_*/bank_* whose ROM address has a name in decomp/symbols.txt is renamed
to it (continuation roots inside a function become Function_AAAA), so
the generated C uses the same names. Run tools/regen.sh after
(sync_symbols rewrites the cfg blocks from symbols.toml).
"""
import bisect, pathlib, re, sys, tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'decomp'))
from gen_disasm import load_symbols, to_offset

TOML = ROOT / 'recomp' / 'symbols.toml'


def main():
    names = {off: name for off, (name, _) in load_symbols().items() if off is not None}
    starts = sorted(names)
    text = TOML.read_text()
    funcs = tomllib.loads(text)['func']
    taken = {f['name'] for f in funcs}
    renamed = 0
    for f in funcs:
        off = to_offset(f['bank'] << 16 | int(f['addr'], 16))
        new = names.get(off)
        if new is None and off is not None:
            # A continuation root inside a named function: Function_AAAA.
            i = bisect.bisect_right(starts, off) - 1
            if i >= 0 and starts[i] // 0x8000 == off // 0x8000:
                new = f'{names[starts[i]]}_{int(f["addr"], 16):04X}'
        if not new or not re.match(r'(sub|bank)_', f['name']) or new in taken:
            continue
        text, n = re.subn(rf'^name = "{re.escape(f["name"])}"$', f'name = "{new}"', text, flags=re.M)
        if n == 1:
            taken.add(new)
            renamed += 1
    TOML.write_text(text)
    print(f'renamed {renamed} recomp functions')


if __name__ == '__main__':
    main()
