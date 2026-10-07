"""Split the disassembly into naming chunks and assign symbol ownership.

usage: ownership.py LISTING_DIR N_CHUNKS OUT_DIR

Reads the generated listing (build/disasm/bank_*.asm), splits the functions
into N contiguous chunks of about equal code size, and writes OUT_DIR/chunk_I.asm
(the chunk's slice of the listing) plus OUT_DIR/ownership.json:
  {"I": {"start": "BBAAAA", "end": "BBAAAA", "functions": [...unnamed sub_...],
         "ram": [["7E009B", uses], ...]}}
A RAM variable (direct page / absolute below $2000 / long WRAM or SRAM; D is
always $0000 in this game) is owned by the chunk that references it most.
"""
import collections, json, pathlib, re, sys

BRANCHES = {'bcc', 'bcs', 'beq', 'bmi', 'bne', 'bpl', 'bra', 'brl', 'bvc', 'bvs'}
LINE = re.compile(r'^  (\w+)(?:\.([bwl]))? ?([^;]*?)\s*; \$([0-9A-F]{6})')


def ram_ref(mn, size, operand):
    """WRAM/SRAM address (24-bit) an operand names, or None."""
    m = re.match(r'^[\[(]?\$([0-9A-F]+)', operand.strip())
    if not m or mn in BRANCHES or mn in ('jsr', 'jmp', 'jsl', 'jml', 'pea', 'per', 'mvn', 'mvp'):
        return None
    v, digits = int(m.group(1), 16), len(m.group(1))
    if digits == 2:
        return 0x7E0000 | v
    if digits == 4:
        return 0x7E0000 | v if v < 0x2000 else None
    if digits == 6:
        bank = v >> 16
        if bank in (0x7E, 0x7F) or 0x70 <= bank <= 0x77:
            return v
        if (bank & 0x7F) < 0x40 and (v & 0xFFFF) < 0x2000:
            return 0x7E0000 | (v & 0xFFFF)
    return None


def main(listing, n, out):
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []  # (pc24, line, function-start?)
    for f in sorted(pathlib.Path(listing).glob('bank_8[0-3].asm')):
        func_start = False
        for line in f.read_text().splitlines():
            if line.startswith('; ' + '-' * 70):
                func_start = True
            m = LINE.match(line)
            rows.append((int(m.group(4), 16) if m else None, line, func_start and bool(m)))
            if m:
                func_start = False
    code_rows = [r for r in rows if r[0] is not None]
    target = len(code_rows) / int(n)
    chunks, cur, count = [], [], 0
    for r in rows:
        if r[2] and count >= target and len(chunks) < int(n) - 1:
            chunks.append(cur)
            cur, count = [], 0
        cur.append(r)
        count += r[0] is not None
    chunks.append(cur)
    uses = collections.defaultdict(collections.Counter)
    owned = {}
    for i, chunk in enumerate(chunks):
        funcs = []
        prev = None
        for pc, line, _ in chunk:
            if line.endswith(':') and line.startswith('sub_'):
                funcs.append(line[:-1])
            m = LINE.match(line)
            if m:
                a = ram_ref(m.group(1), m.group(2), m.group(3))
                if a is not None:
                    uses[a][i] += 1
        pcs = [pc for pc, _, _ in chunk if pc is not None]
        owned[str(i)] = {'start': f'{pcs[0]:06X}', 'end': f'{pcs[-1]:06X}', 'functions': funcs,
                         'ram': []}
        (out / f'chunk_{i}.asm').write_text('\n'.join(l for _, l, _ in chunk) + '\n')
    for a, by in sorted(uses.items()):
        i, k = by.most_common(1)[0]
        owned[str(i)]['ram'].append([f'{a:06X}', sum(by.values())])
    (out / 'ownership.json').write_text(json.dumps(owned, indent=1))
    for i, o in owned.items():
        print(i, o['start'], o['end'], len(o['functions']), 'funcs', len(o['ram']), 'ram')


if __name__ == '__main__':
    main(*sys.argv[1:4])
