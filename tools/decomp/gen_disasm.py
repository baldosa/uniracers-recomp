"""Generate the Asar disassembly from the recompiler's decode.

usage: gen_disasm.py ROM DECODE.json OUTDIR

Writes OUTDIR/main.asm and OUTDIR/bank_XX.asm (one per 32 KiB LoROM bank,
addressed in the FastROM mirror $80-$BF where the game runs). Every
instruction the recomp compiles (decode_dump.py) becomes source with explicit
operand sizes so Asar reproduces it byte for byte; branch/jump/call targets
that are instruction starts get labels (names from recomp/symbols.toml where
known, CODE_BBAAAA otherwise). Everything else -- data, and code not yet
reached -- is `incbin`ed from the owner's ROM at build time, so no ROM bytes
are written into the source tree.
"""
import json, os, pathlib, sys, tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from dis65816 import OPS  # (mnemonic, mode) per opcode

BANK = 0x8000
LEN = {'imp': 1, 'acc': 1, 'imm8': 2, 'dp': 2, 'dpx': 2, 'dpy': 2, 'dpi': 2, 'dpxi': 2,
       'dpiy': 2, 'dpil': 2, 'dpily': 2, 'sr': 2, 'sriy': 2, 'abs': 3, 'absx': 3,
       'absy': 3, 'absi': 3, 'absxi': 3, 'absil': 3, 'long': 4, 'longx': 4, 'mv': 3,
       'rel': 2, 'rell': 3}


def snes(off):
    """ROM offset -> SNES address in the $80-$BF FastROM mirror."""
    return ((0x80 + off // BANK) << 16) | 0x8000 | (off % BANK)


def insn_length(op, m, x):
    mnem, mode = OPS[op]
    if mode == 'immm':
        return 2 if m else 3
    if mode == 'immx':
        return 2 if x else 3
    return LEN[mode]


def target(off, raw, mode):
    """Static code target (ROM offset) of a branch/jump/call, or None."""
    pc = snes(off)
    bank = pc & 0xFF0000
    nxt = (pc & 0xFFFF) + len(raw)
    if mode == 'rel':
        d = raw[1] - 256 if raw[1] > 127 else raw[1]
        return bank | ((nxt + d) & 0xFFFF)
    if mode == 'rell':
        v = raw[1] | raw[2] << 8
        d = v - 65536 if v > 32767 else v
        return bank | ((nxt + d) & 0xFFFF)
    return None


def to_offset(pc24):
    if (pc24 & 0xFFFF) < 0x8000 or ((pc24 >> 16) & 0x7F) >= 0x40:
        return None
    return ((pc24 >> 16) & 0x7F) * BANK + (pc24 & 0x7FFF)


def fmt(raw, m, x, mode_target_label):
    op = raw[0]
    mnem, mode = OPS[op]
    mn = mnem.lower()
    b = raw[1:]
    v8 = b[0] if b else 0
    v16 = (b[0] | b[1] << 8) if len(b) >= 2 else 0
    v24 = (b[0] | b[1] << 8 | b[2] << 16) if len(b) >= 3 else 0
    lbl = mode_target_label
    if mode == 'imp':
        return mn
    if mode == 'acc':
        return f'{mn} a'
    if mode == 'imm8':
        return f'{mn} #${v8:02X}'
    if mode in ('immm', 'immx'):
        return f'{mn}.b #${v8:02X}' if len(raw) == 2 else f'{mn}.w #${v16:04X}'
    if mode == 'dp':
        return f'{mn}.b ${v8:02X}'
    if mode == 'dpx':
        return f'{mn}.b ${v8:02X},x'
    if mode == 'dpy':
        return f'{mn}.b ${v8:02X},y'
    if mode == 'dpi':
        return f'{mn} (${v8:02X})'
    if mode == 'dpxi':
        return f'{mn} (${v8:02X},x)'
    if mode == 'dpiy':
        return f'{mn} (${v8:02X}),y'
    if mode == 'dpil':
        return f'{mn} [${v8:02X}]'
    if mode == 'dpily':
        return f'{mn} [${v8:02X}],y'
    if mode == 'sr':
        return f'{mn} ${v8:02X},s'
    if mode == 'sriy':
        return f'{mn} (${v8:02X},s),y'
    if mode == 'abs':
        if mn in ('jsr', 'jmp') and lbl:
            return f'{mn} {lbl}'
        if mn in ('jsr', 'jmp', 'pea'):
            return f'{mn} ${v16:04X}'
        return f'{mn}.w ${v16:04X}'
    if mode == 'absx':
        return f'{mn}.w ${v16:04X},x'
    if mode == 'absy':
        return f'{mn}.w ${v16:04X},y'
    if mode == 'absi':
        return f'{mn} (${v16:04X})'
    if mode == 'absxi':
        return f'{mn} (${v16:04X},x)'
    if mode == 'absil':
        return f'{mn} [${v16:04X}]'
    if mode == 'long':
        if mn in ('jsl', 'jml'):
            return f'{mn} {lbl}' if lbl else f'{mn} ${v24:06X}'
        return f'{mn}.l ${v24:06X}'
    if mode == 'longx':
        return f'{mn}.l ${v24:06X},x'
    if mode == 'mv':
        return f'{mn} ${b[0]:02X},${b[1]:02X}'   # Asar: machine byte order
    if mode in ('rel', 'rell'):
        return f'{mn} {lbl}'
    raise ValueError(mode)


def load_names():
    names = {}
    p = ROOT / 'recomp' / 'symbols.toml'
    if p.exists():
        for f in tomllib.loads(p.read_text()).get('func', []):
            off = to_offset((f['bank'] << 16) | int(f['addr'], 16))
            if off is not None and not f['name'].startswith('sub_'):
                names[off] = f['name']
    return names


def main(rom_path, decode_path, outdir):
    rom = pathlib.Path(rom_path).read_bytes()
    dec = json.loads(pathlib.Path(decode_path).read_text())
    # Accept decoded instructions whose bytes agree with the opcode's length
    # at the recorded widths and that do not overlap an earlier one.
    code = {}
    end = -1
    rejected = []
    for off_s, (length, m, x, *_) in sorted(dec['insns'].items(), key=lambda kv: int(kv[0])):
        off = int(off_s)
        if off < end or off + length > len(rom) or insn_length(rom[off], m, x) != length:
            rejected.append(off)
            continue
        if (off % BANK) + length > BANK:
            rejected.append(off)  # would straddle a bank boundary
            continue
        code[off] = (length, m, x)
        end = off + length
    names = load_names()
    starts = sorted(code)
    import bisect

    def anchor(to):
        """Label offset and byte delta for a target: the target itself when it
        is an instruction start or lies in incbin data, else the start of the
        instruction it falls inside (a mid-instruction entry)."""
        i = bisect.bisect_right(starts, to) - 1
        if i >= 0 and starts[i] < to < starts[i] + code[starts[i]][0]:
            return starts[i], to - starts[i]
        return to, 0

    def static_target(off, raw):
        mnem, mode = OPS[raw[0]]
        if mode in ('rel', 'rell'):
            return target(off, raw, mode)
        if mode == 'abs' and mnem in ('JSR', 'JMP'):
            return (snes(off) & 0xFF0000) | (raw[1] | raw[2] << 8)
        if mode == 'long' and mnem in ('JSL', 'JML'):
            return raw[1] | raw[2] << 8 | raw[3] << 16
        return None

    # Labels at every static target inside the ROM (code or data).
    labels = {}
    refs = {}
    for off, (length, m, x) in code.items():
        t = static_target(off, rom[off:off + length])
        to = to_offset(t) if t is not None else None
        if to is None or to >= len(rom):
            continue
        a, delta = anchor(to)
        labels.setdefault(a, names.get(a, f'CODE_{snes(a):06X}'))
        refs[off] = (a, delta, t)
    for off, name in names.items():
        if off in code:
            labels[off] = name

    def ref_expr(off):
        """Source operand for a static target: label (+delta), masked to the
        target's bank when the code addresses the $00 mirror."""
        if off not in refs:
            return None
        a, delta, t = refs[off]
        e = labels[a] + (f'+{delta}' if delta else '')
        if (snes(a) + delta) != t and (snes(a) + delta) & 0x7FFFFF == t:
            e = f'{e}&$7FFFFF'
        return e

    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    banks = len(rom) // BANK
    main_lines = ['; Uniracers (USA) -- generated by tools/decomp/gen_disasm.py', 'lorom', '']
    stats = {'code_bytes': 0, 'incbin_bytes': 0}
    for bank in range(banks):
        name = f'bank_{0x80 + bank:02X}.asm'
        lines = [f'; bank ${0x80 + bank:02X} (ROM ${bank * BANK:06X}-${bank * BANK + BANK - 1:06X})',
                 f'org ${0x80 + bank:02X}8000', '']
        off, stop = bank * BANK, bank * BANK + BANK
        while off < stop:
            if off in code:
                if off in labels:
                    lines.append(f'{labels[off]}:')
                length, m, x = code[off]
                raw = rom[off:off + length]
                lbl = ref_expr(off)
                lines.append(f'  {fmt(raw, m, x, lbl):<28}; ${snes(off):06X}')
                stats['code_bytes'] += length
                off += length
            else:
                start = off
                if off in labels:
                    lines.append(f'{labels[off]}:')
                off += 1
                while off < stop and off not in code and off not in labels:
                    off += 1
                lines.append(f'  incbin "../baserom.sfc":${start:06X}..${off:06X}')
                stats['incbin_bytes'] += off - start
        (out / name).write_text('\n'.join(lines) + '\n')
        main_lines.append(f'incsrc "{name}"')
    (out / 'main.asm').write_text('\n'.join(main_lines) + '\n')
    stats['labels'] = len(labels)
    stats['rejected_decodes'] = len(rejected)
    stats['conflicts'] = len(dec.get('conflicts', {}))
    print(json.dumps(stats))


if __name__ == '__main__':
    main(*sys.argv[1:4])
