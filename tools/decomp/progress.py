"""Decomp progress from the generated listing.

usage: progress.py [LISTING_DIR] [--json]

Uniracers is hand-written 65816, so there is no C to match: the measures are
how much of the code is disassembled source (the rest of the ROM is data,
incbin'd), how many functions are named and commented, and how many RAM
variables are named. Reads build/disasm (tools/decomp/build.sh) and
decomp/ram.txt.
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def main(args):
    listing = pathlib.Path(next((a for a in args if not a.startswith('--')), ROOT / 'build' / 'disasm'))
    code = incbin = 0
    funcs = named = commented = 0
    for f in sorted(p for p in listing.glob('*.asm') if p.name not in ('main.asm', 'hw.asm', 'ram.asm')):
        lines = f.read_text().splitlines()
        for i, line in enumerate(lines):
            if line.startswith('  incbin'):
                a, b = re.findall(r'\$([0-9A-F]+)', line)
                incbin += int(b, 16) - int(a, 16)
            elif line.startswith('  ') and '; $' in line:
                text = line.split(';')[0].split()
                code += 1 if text else 0
            elif line.startswith('; ' + '-' * 70):
                header = lines[i + 1][2:]
                funcs += 1
                name, _, comment = header.partition(': ')
                named += not name.startswith('sub_')
                commented += bool(comment.strip())
    ram_named = 0
    ram = ROOT / 'decomp' / 'ram.txt'
    if ram.exists():
        ram_named = sum(1 for l in ram.read_text().splitlines() if l.strip() and not l.startswith('#'))
    report = {'instructions': code, 'data_bytes_incbin': incbin, 'functions': funcs,
              'functions_named': named, 'functions_commented': commented,
              'ram_variables_named': ram_named}
    if '--json' in args:
        print(json.dumps(report))
        return
    pct = lambda a, b: f'{100 * a / b:.1f}%' if b else 'n/a'
    print(f'instructions as source : {code}')
    print(f'data (incbin) bytes    : {incbin}')
    print(f'functions named        : {named}/{funcs} ({pct(named, funcs)})')
    print(f'functions commented    : {commented}/{funcs} ({pct(commented, funcs)})')
    print(f'RAM variables named    : {ram_named}')


if __name__ == '__main__':
    main(sys.argv[1:])
