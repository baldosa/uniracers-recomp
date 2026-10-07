"""Promote coverage discoveries into durable AOT roots in recomp/symbols.toml.

usage: promote_roots.py CAPTURE.json CAPTURE.jsonl [...]

A coverage capture only lists code the current build still interprets, so
regenerating from the latest captures alone drops roots found earlier. Each
clean discovery (native mode, no bails, ROM address) becomes durable:
a new address gets a [[func]] sub_BBAAAA (emit = true) in its hottest entry
mode, and every other mode it was entered in becomes a [[variant]] table.
Frame-resume landings recorded by the native hand-off (site == target) count
even without hits. Existing entries are never changed.
"""
import json, os, subprocess, sys, tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SYMBOLS = os.path.join(ROOT, 'recomp', 'symbols.toml')
PROMOTE = {'candidate_requires_analysis_and_replay', 'landing_requires_function_boundary'}

def candidates(discoveries):
    """{(bank, addr): {(m, x): hits}} for promotable discoveries."""
    out = {}
    for d in discoveries:
        resume = d['site_pc24'] == d['target_pc24']
        if (d['candidate_status'] not in PROMOTE and not resume) or d['emulation'] or d['bail_hits']:
            continue
        pc, mx = d['variant'].split(':')
        pc = int(pc, 16)
        bank, addr = pc >> 16, pc & 0xFFFF
        if (bank & 0x7F) >= 0x7E or addr < 0x8000:  # WRAM / non-ROM: not a static root
            continue
        modes = out.setdefault((bank, addr), {})
        mode = (int(mx[1]), int(mx[3]))
        modes[mode] = modes.get(mode, 0) + d['observed_hits']
    return out

def plan(cands, toml_text):
    """([(key, mode)] new funcs, [(key, mode)] new variants) against symbols.toml."""
    data = tomllib.loads(toml_text)
    have = {}
    for f in data.get('func', []):
        key = (f['bank'], int(f['addr'], 16))
        have.setdefault(key, set()).add((f.get('entry_m', 1), f.get('entry_x', 1)))
    for v in data.get('variant', []):
        have.setdefault((v['bank'], int(v['addr'], 16)), set()).add((v['entry_m'], v['entry_x']))
    funcs, variants = [], []
    for key, modes in sorted(cands.items()):
        present = have.get(key)
        if present is None:
            hottest = max(sorted(modes), key=lambda m: modes[m])
            funcs.append((key, hottest))
            present = {hottest}
        variants += [(key, m) for m in sorted(modes) if m not in present]
    return funcs, variants

def render(funcs, variants):
    out = []
    for (bank, addr), (m, x) in funcs:
        out.append(f'\n[[func]]\nname = "sub_{bank:02X}{addr:04X}"\naddr = "{addr:04X}"\n'
                   f'bank = {bank}\nemit = true\nentry_m = {m}\nentry_x = {x}\n'
                   f'note = "coverage discovery"\n')
    for (bank, addr), (m, x) in variants:
        out.append(f'\n[[variant]]\nbank = {bank}\naddr = "{addr:04X}"\nentry_m = {m}\nentry_x = {x}\n')
    return ''.join(out)

def discoveries(captures):
    """Ingest each capture (stem.json + stem.jsonl) on its own: captures from
    different builds carry different identities and cannot be merged."""
    groups = {}
    for c in captures:
        groups.setdefault(os.path.splitext(c)[0], []).append(c)
    out = []
    for files in groups.values():
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'snesrecomp/tools/tier2_ingest.py'),
                            *sorted(files), '--cfg-dir', os.path.join(ROOT, 'recomp'), '--json'],
                           capture_output=True, text=True, check=True)
        out += json.loads(r.stdout)['discoveries']
    return out

def main(captures):
    text = open(SYMBOLS).read()
    funcs, variants = plan(candidates(discoveries(captures)), text)
    open(SYMBOLS, 'a').write(render(funcs, variants))
    print(f'promoted {len(funcs)} roots, {len(variants)} variants')

if __name__ == '__main__':
    main(sys.argv[1:])
