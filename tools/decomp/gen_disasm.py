"""Generate the Asar disassembly from the decode.

usage: gen_disasm.py ROM DECODE.json OUTDIR

Writes OUTDIR/main.asm and OUTDIR/bank_XX.asm (one per 32 KiB LoROM bank,
addressed in the FastROM mirror $80-$BF where the game runs). Every decoded
instruction (decode_dump.py) becomes source with explicit operand sizes so
Asar reproduces it byte for byte. Names and comments come from
decomp/symbols.txt; function entries (call and dispatch targets, vectors,
recovered routines) get sub_BBAAAA headers, other code targets CODE_BBAAAA,
ROM tables read with long addressing DATA_BBAAAA, I/O registers their
fullsnes names (decomp/hw.asm) and RAM variables theirs (decomp/ram.txt). Everything that is not code is `incbin`ed
from the owner's ROM at build time, so no ROM bytes are written into the
source tree.
"""
import bisect, json, pathlib, re, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from dis65816 import OPS  # (mnemonic, mode) per opcode

BANK = 0x8000
LEN = {'imp': 1, 'acc': 1, 'imm8': 2, 'dp': 2, 'dpx': 2, 'dpy': 2, 'dpi': 2, 'dpxi': 2,
       'dpiy': 2, 'dpil': 2, 'dpily': 2, 'sr': 2, 'sriy': 2, 'abs': 3, 'absx': 3,
       'absy': 3, 'absi': 3, 'absxi': 3, 'absil': 3, 'long': 4, 'longx': 4, 'mv': 3,
       'rel': 2, 'rell': 3}
VECTORS = range(0x7FE4, 0x8000, 2)  # native and emulation vectors in the header


def snes(off):
    """ROM offset -> SNES address in the $80-$BF FastROM mirror."""
    return ((0x80 + off // BANK) << 16) | 0x8000 | (off % BANK)


def to_offset(pc24):
    if (pc24 & 0xFFFF) < 0x8000 or ((pc24 >> 16) & 0x7F) >= 0x40:
        return None
    return ((pc24 >> 16) & 0x7F) * BANK + (pc24 & 0x7FFF)


def insn_length(op, m, x):
    mode = OPS[op][1]
    if mode == 'immm':
        return 2 if m else 3
    if mode == 'immx':
        return 2 if x else 3
    return LEN[mode]


def target(off, raw, mode):
    """Target of a relative branch (or PER) at ROM offset `off`."""
    pc = snes(off)
    nxt = (pc & 0xFFFF) + len(raw)
    if mode == 'rel':
        d = raw[1] - 256 if raw[1] > 127 else raw[1]
    else:
        v = raw[1] | raw[2] << 8
        d = v - 65536 if v > 32767 else v
    return (pc & 0xFF0000) | ((nxt + d) & 0xFFFF)


def static_ref(off, raw):
    """(pc24, kind) of the ROM address an instruction names statically:
    'code' for branches/jumps/calls, 'data' for long-addressed operands."""
    mnem, mode = OPS[raw[0]]
    if mode in ('rel', 'rell'):
        return target(off, raw, mode), 'code'
    if mode == 'abs' and mnem in ('JSR', 'JMP'):
        return (snes(off) & 0xFF0000) | raw[1] | raw[2] << 8, 'code'
    if mode in ('long', 'longx'):
        t = raw[1] | raw[2] << 8 | raw[3] << 16
        return t, 'code' if mnem in ('JSL', 'JML') else 'data'
    return None


def fmt(raw, m, x, ref=None, sym=None):
    """Asar source for one instruction. `ref` replaces a static code/ROM
    address operand with a label expression; `sym` replaces a data operand
    (I/O register or RAM variable) with its define."""
    mnem, mode = OPS[raw[0]]
    mn = mnem.lower()
    b = raw[1:]
    v8 = b[0] if b else 0
    v16 = (b[0] | b[1] << 8) if len(b) >= 2 else 0
    v24 = (b[0] | b[1] << 8 | b[2] << 16) if len(b) >= 3 else 0
    o8, o16, o24 = (sym, sym, sym) if sym else (f'${v8:02X}', f'${v16:04X}', f'${v24:06X}')
    if mode == 'imp':
        return mn
    if mode == 'acc':
        return f'{mn} a'
    if mode == 'imm8':
        return f'{mn} #${v8:02X}'
    if mode in ('immm', 'immx'):
        return f'{mn}.b #${v8:02X}' if len(raw) == 2 else f'{mn}.w #${v16:04X}'
    simple = {'dp': '{}', 'dpx': '{},x', 'dpy': '{},y'}
    if mode in simple:
        return f'{mn}.b ' + simple[mode].format(o8)
    ind = {'dpi': '({})', 'dpxi': '({},x)', 'dpiy': '({}),y', 'dpil': '[{}]', 'dpily': '[{}],y'}
    if mode in ind:
        return f'{mn}.b ' + ind[mode].format(o8) if sym else f'{mn} ' + ind[mode].format(o8)
    if mode == 'sr':
        return f'{mn} ${v8:02X},s'
    if mode == 'sriy':
        return f'{mn} (${v8:02X},s),y'
    if mode == 'abs':
        if mn in ('jsr', 'jmp'):
            return f'{mn} {ref or f"${v16:04X}"}'
        if mn == 'pea':
            return f'{mn} ${v16:04X}'
        return f'{mn}.w {o16}'
    if mode == 'absx':
        return f'{mn}.w {o16},x'
    if mode == 'absy':
        return f'{mn}.w {o16},y'
    if mode in ('absi', 'absxi', 'absil'):
        form = {'absi': '({})', 'absxi': '({},x)', 'absil': '[{}]'}[mode]
        return f'{mn}.w ' + form.format(o16) if sym else f'{mn} ' + form.format(o16)
    if mode == 'long':
        if mn in ('jsl', 'jml'):
            return f'{mn} {ref or o24}'
        return f'{mn}.l {ref or o24}'
    if mode == 'longx':
        return f'{mn}.l {ref or o24},x'
    if mode == 'mv':
        return f'{mn} ${b[0]:02X},${b[1]:02X}'   # Asar: machine byte order
    if mode in ('rel', 'rell'):
        return f'{mn} {ref}'
    raise ValueError(mode)


def data_operand(raw):
    """24-bit address a data operand names (RAM or I/O; D = $0000 and the
    low 8 KiB of WRAM is mirrored in every bank this game runs with), and
    whether the operand is long (so the define must match its bank)."""
    mnem, mode = OPS[raw[0]]
    if mnem in ('JSR', 'JMP', 'JSL', 'JML', 'PEA', 'PER', 'PEI') and mode not in ('absi', 'absxi', 'absil'):
        return None
    if mode in ('dp', 'dpx', 'dpy', 'dpi', 'dpxi', 'dpiy', 'dpil', 'dpily'):
        return 0x7E0000 | raw[1], False
    if mode in ('abs', 'absx', 'absy', 'absi', 'absxi', 'absil'):
        v = raw[1] | raw[2] << 8
        if v < 0x2000:
            return 0x7E0000 | v, False
        return (v, False) if 0x2100 <= v < 0x4400 else None
    if mode in ('long', 'longx'):
        return raw[1] | raw[2] << 8 | raw[3] << 16, True
    return None


def load_symbols():
    """decomp/symbols.txt: `BBAAAA name [; comment]` per line."""
    out = {}
    p = ROOT / 'decomp' / 'symbols.txt'
    for line in p.read_text().splitlines() if p.exists() else ():
        body, _, comment = line.partition(';')
        if body.strip() and not line.lstrip().startswith('#'):
            addr, name = body.split()[:2]
            out[to_offset(int(addr, 16))] = (name, comment.strip())
    return out


def load_ram():
    """decomp/ram.txt: `BBAAAA name [size] [; comment]` per line (WRAM 7E/7F,
    SRAM 70-77). Returns (sorted [(addr, size, name)], asm define text)."""
    out, defs = [], ['; RAM variables (decomp/ram.txt), used by the disassembly.']
    p = ROOT / 'decomp' / 'ram.txt'
    for line in p.read_text().splitlines() if p.exists() else ():
        body, _, comment = line.partition(';')
        if body.strip() and not line.lstrip().startswith('#'):
            f = body.split()
            out.append((int(f[0], 16), int(f[2]) if len(f) > 2 else 1, f[1]))
            defs.append(f'!{f[1]} = ${int(f[0], 16):06X}' + (f'  ; {comment.strip()}' if comment.strip() else ''))
    return sorted(out), '\n'.join(defs) + '\n'


def load_subsystems():
    """decomp/subsystems.txt: {offset: (file, description)}."""
    out = {}
    p = ROOT / 'decomp' / 'subsystems.txt'
    for line in p.read_text().splitlines() if p.exists() else ():
        body, _, desc = line.partition(';')
        if body.strip() and not line.lstrip().startswith('#'):
            addr, name = body.split()[:2]
            out[to_offset(int(addr, 16))] = (name, desc.strip())
    return out


def load_hw():
    hw = {}
    for line in (ROOT / 'decomp' / 'hw.asm').read_text().splitlines():
        m = re.match(r'!(\w+) = \$([0-9A-F]{4})', line)
        if m:
            hw[int(m.group(2), 16)] = m.group(1)
    return hw


def dispatch_targets():
    out = set()
    for cfg in (ROOT / 'recomp').glob('bank*.cfg'):
        for line in cfg.read_text().splitlines():
            if line.startswith('indirect_dispatch') and 'targets:' in line:
                out.update(int(t, 16) for t in line.split('targets:')[1].split()[0].split(','))
    return out


def main(rom_path, decode_path, outdir):
    rom = pathlib.Path(rom_path).read_bytes()
    dec = json.loads(pathlib.Path(decode_path).read_text())
    # Accept decoded instructions whose bytes agree with the opcode's length
    # at the recorded widths and do not overlap an earlier one; the rest are
    # overlapping entries (code that jumps into an instruction's operand).
    code, overlaps, end = {}, {}, -1
    for off_s, (length, m, x, *_) in sorted(dec['insns'].items(), key=lambda kv: int(kv[0])):
        off = int(off_s)
        if (off + length > len(rom) or insn_length(rom[off], m, x) != length
                or (off % BANK) + length > BANK):
            continue
        if off < end:
            overlaps.setdefault(max(o for o in code if o < off), []).append(off)
            continue
        code[off] = (length, m, x)
        end = off + length
    starts = sorted(code)

    def anchor(to):
        """Label offset and delta for a target: the target itself when it is
        an instruction start or data, else the instruction it falls inside."""
        i = bisect.bisect_right(starts, to) - 1
        if i >= 0 and starts[i] < to < starts[i] + code[starts[i]][0]:
            return starts[i], to - starts[i]
        return to, 0

    symbols, hw = load_symbols(), load_hw()
    ram, ram_defs = load_ram()
    ram_addrs = [a for a, _, _ in ram]

    def sym_expr(raw):
        """Define expression for a data operand, or None."""
        r = data_operand(raw)
        if r is None:
            return None
        a, long = r
        if a < 0x10000:
            return f'!{hw[a]}' if a in hw and not long else None
        i = bisect.bisect_right(ram_addrs, a) - 1
        if i < 0:
            return None
        base, size, name = ram[i]
        if not base <= a < base + size:
            return None
        if long and (base >> 16) != (a >> 16):
            return None
        return f'!{name}' + (f'+{a - base}' if a > base else '')
    entries = {to_offset(t) for t in dispatch_targets()}
    entries |= {to_offset(rom[v] | rom[v + 1] << 8) for v in VECTORS}
    dead = pathlib.Path(decode_path).with_name('dead.json')
    if dead.exists():
        entries |= {to_offset(int(e['entry'], 16)) for e in json.loads(dead.read_text())
                    if e['depth'] == 0}
    labels, refs = {}, {}
    for off, (length, m, x) in code.items():
        raw = rom[off:off + length]
        r = static_ref(off, raw)
        to = to_offset(r[0]) if r else None
        if to is None or to >= len(rom):
            continue
        a, delta = anchor(to)
        kind = r[1] if a not in code else 'code'
        if OPS[raw[0]][0] in ('JSR', 'JSL') and delta == 0:
            entries.add(a)
        labels.setdefault(a, f'{"CODE" if kind == "code" else "DATA"}_{snes(a):06X}')
        refs[off] = (a, delta, r[0])
    entries &= set(code)
    for off in entries:
        labels[off] = f'sub_{snes(off):06X}'
    for off, (name, _) in symbols.items():
        if off is not None and (off in code or off in labels):
            labels[off] = name

    def ref_expr(off):
        """Label (+delta) for a static operand, masked to the $00 mirror when
        the code names the bank-$00 address of the label."""
        if off not in refs:
            return None
        a, delta, t = refs[off]
        e = labels[a] + (f'+{delta}' if delta else '')
        if snes(a) + delta != t:
            e = f'{e}&$7FFFFF'
        return e

    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / 'decomp' / 'hw.asm', out / 'hw.asm')
    (out / 'ram.asm').write_text(ram_defs)
    main_lines = ['; Uniracers (USA) -- generated by tools/decomp/gen_disasm.py', 'lorom',
                  'incsrc "hw.asm"', 'incsrc "ram.asm"', '']
    stats = {'code_bytes': 0, 'incbin_bytes': 0}
    # Output files: one per subsystem (decomp/subsystems.txt: `BBAAAA file
    # ; description`, each running to the next), bank_XX where none starts.
    splits = load_subsystems()
    files, cur = {}, None
    off = 0
    while off < len(rom):
        bank, stop = off // BANK, min(off // BANK * BANK + BANK, len(rom))
        nxt = min([o for o in splits if o > off] + [stop])
        if off in splits:
            cur, desc = splits[off]
            header = f'; {cur}: {desc}' if desc else f'; {cur}'
        elif cur is None or (off % BANK == 0 and not splits):
            cur = f'bank_{0x80 + bank:02X}.asm'
            header = f'; bank ${0x80 + bank:02X} (ROM ${bank * BANK:06X}-${stop - 1:06X})'
        if cur not in files:
            files[cur] = [header, '']
            main_lines.append(f'incsrc "{cur}"')
        lines = files[cur]
        lines += [f'org ${snes(off):06X}', '']
        while off < nxt:
            if off in labels:
                if off in entries or off in symbols:
                    comment = symbols.get(off, ('', ''))[1]
                    lines += ['', f'; {"-" * 70}', f'; {labels[off]}' + (f': {comment}' if comment else '')]
                lines.append(f'{labels[off]}:')
            if off in code:
                length, m, x = code[off]
                raw = rom[off:off + length]
                text = fmt(raw, m, x, ref_expr(off), sym_expr(raw))
                note = f'; ${snes(off):06X}'
                if off in overlaps:
                    note += ' (also entered at ' + ', '.join(f'${snes(o):06X}' for o in overlaps[off]) + ')'
                lines.append(f'  {text:<28}{note}')
                stats['code_bytes'] += length
                off += length
            else:
                start = off
                off += 1
                while off < nxt and off not in code and off not in labels:
                    off += 1
                lines.append(f'  incbin "../baserom.sfc":${start:06X}..${off:06X}')
                stats['incbin_bytes'] += off - start
    for name, lines in files.items():
        (out / name).write_text('\n'.join(lines) + '\n')
    (out / 'main.asm').write_text('\n'.join(main_lines) + '\n')
    stats['functions'] = len(entries)
    stats['named'] = sum(1 for o in entries if not labels[o].startswith('sub_'))
    stats['labels'] = len(labels)
    stats['overlapping_entries'] = sum(map(len, overlaps.values()))
    print(json.dumps(stats))


if __name__ == '__main__':
    main(*sys.argv[1:4])
