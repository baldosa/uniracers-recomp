"""Promote coverage discoveries into durable AOT roots in recomp/symbols.toml.

usage: promote_roots.py CAPTURE.json CAPTURE.jsonl [...]

A coverage capture only lists code the current build still interprets, so
regenerating from the latest captures alone drops roots found earlier. Each
clean discovery (native mode, no bails, ROM address) is appended once as
[[func]] sub_BBAAAA with emit = true and its entry M/X; the hottest mode wins
when an address was seen in several. Existing entries are never changed.
"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SYMBOLS = os.path.join(ROOT, 'recomp', 'symbols.toml')
PROMOTE = {'candidate_requires_analysis_and_replay', 'landing_requires_function_boundary'}

def candidates(discoveries):
    """{(bank, addr): (m, x)} for promotable discoveries, hottest mode per address."""
    best = {}
    for d in discoveries:
        # A frame-resume landing (native hand-off records site == target) is
        # where the guest really continued, even with no counted hits.
        resume = d['site_pc24'] == d['target_pc24']
        if (d['candidate_status'] not in PROMOTE and not resume) or d['emulation'] or d['bail_hits']:
            continue
        pc, mx = d['variant'].split(':')
        pc = int(pc, 16)
        bank, addr = pc >> 16, pc & 0xFFFF
        if (bank & 0x7F) >= 0x7E or addr < 0x8000:  # WRAM / non-ROM: not a static root
            continue
        hits = d['observed_hits']
        if (bank, addr) not in best or hits > best[(bank, addr)][0]:
            best[(bank, addr)] = (hits, int(mx[1]), int(mx[3]))
    return {k: (m, x) for k, (_, m, x) in best.items()}

def existing(text):
    return {(int(b), int(a, 16)) for a, b in re.findall(r'addr = "([0-9A-Fa-f]+)"\s*\nbank = (\d+)', text)}

def entries(new, have):
    out = []
    for (bank, addr), (m, x) in sorted(new.items()):
        if (bank, addr) in have:
            continue
        out.append(f'\n[[func]]\nname = "sub_{bank:02X}{addr:04X}"\naddr = "{addr:04X}"\n'
                   f'bank = {bank}\nemit = true\nentry_m = {m}\nentry_x = {x}\n'
                   f'note = "coverage discovery"\n')
    return out

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
    add = entries(candidates(discoveries(captures)), existing(text))
    open(SYMBOLS, 'a').write(''.join(add))
    print(f'promoted {len(add)} roots')

if __name__ == '__main__':
    main(sys.argv[1:])
