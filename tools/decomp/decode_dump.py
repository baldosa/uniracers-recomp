"""Dump the recompiler's own instruction decode for the disassembly generator.

usage: decode_dump.py ROM OUT.json [--profiles DIR ...]

Runs snesrecomp's v2_emit in-process (same cfgs and coverage seeds as
tools/regen.sh) with the emitter's decoder wrapped, so every instruction the
recomp compiles is recorded with the M/X widths it was compiled at. Output,
keyed by ROM file offset (LoROM $00/$80 mirrors fold together):

  {"insns": {"<offset>": [length, m, x, source]}, "conflicts": {"<offset>": [[len, m, x], ...]}}

Offsets decoded at different lengths are conflicts: the bytes can only be
one instruction stream, so the generator emits them as data and reports them.
Derived from the ROM's layout only (no ROM bytes), but keep it out of git
with the rest of build/.
"""
import argparse, collections, importlib, json, os, pathlib, re, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "snesrecomp" / "tools"), str(ROOT / "snesrecomp" / "recompiler")]


def lorom_offset(pc24):
    return ((pc24 >> 16) & 0x7F) * 0x8000 + (pc24 & 0x7FFF)


from snes65816 import MODE_STR  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
from dis65816 import OPS  # noqa: E402

MODE_OF = {op: mode for op, (_, mode) in OPS.items()}

BAD = {"BRK", "COP", "WDM", "STP", "WAI"}
TEXT = re.compile(rb"[\x5f\x61-\x7a]{6,}")
CODE_BANKS = range(0, 4)  # ROM banks that hold code (the rest is data)


def looks_like_table(rom, graph, mine):
    """Data that happens to decode cleanly: runs of one opcode with operands
    (fill bytes: SBC $FFFFFF,X x N; value tables: ORA $62,S / $64,S / ...), or
    an entry that starts with words sharing one high byte (a bank-local
    pointer table: $AE30, $AE3E, $AE4C, $AE5C)."""
    insns = sorted((d for d in graph.insns.values() if lorom_offset(d.key.pc & 0xFFFFFF) in mine),
                   key=lambda d: d.key.pc)
    run = same_bytes = 1
    for a, b in zip(insns, insns[1:]):
        same = a.insn.opcode == b.insn.opcode and a.insn.length > 1
        store = a.insn.mnem in ("STA", "STZ", "STX", "STY")  # unrolled clears are code
        run = run + 1 if same and not store else 1
        same_bytes = same_bytes + 1 if same and a.insn.operand == b.insn.operand else 1
        if same_bytes >= 4 or run >= 8:  # fill, or a value table (unrolled code stays shorter)
            return True
    start = lorom_offset(insns[0].key.pc & 0xFFFFFF) if insns else 0
    highs = {rom[start + 2 * i + 1] for i in range(4)}
    return len(highs) == 1 and highs.pop() >= 0x80 and all(
        start + n in mine for n in range(8))


def own_starts_of(graph, mine):
    return {lorom_offset(d.key.pc & 0xFFFFFF) for d in graph.insns.values()} & mine


def call_target(d):
    ins, pc = d.insn, d.key.pc & 0xFFFFFF
    if ins.mnem in ("JSR", "JMP") and MODE_STR[ins.mode] == "abs":
        return (pc & 0xFF0000) | ins.operand
    if ins.mnem in ("JSL", "JML") and ins.length == 4:
        return ins.operand
    return None


def exit_aware_decoder(rom, manifest):
    """decode(pc24, m, x) that knows callee exit widths: the manifest's proven
    exit facts, plus facts computed on demand for callees the recomp never
    analysed (off-route and dead code), so post-call bytes decode at the
    widths the callee really returns in."""
    from v2.decoder import _decode_function_uncached, analyze_function_exit_mx
    facts = {}
    for k, v in manifest["exit_modes"].items():
        facts[(int(k[:6], 16), int(k[8]), int(k[10]))] = (v["m"], v["x"])

    def known(key):
        return key in facts or (key[0] ^ 0x800000, key[1], key[2]) in facts

    def decode(pc24, m, x, depth=0):
        for _ in range(4):
            graph = _decode_function_uncached(rom, pc24 >> 16, pc24 & 0xFFFF, m, x,
                                              callee_exit_mx=facts)
            learned = False
            for d in graph.insns.values():
                if d.insn.mnem not in ("JSR", "JSL"):
                    continue
                t = call_target(d)
                key = (t, d.key.m & 1, d.key.x & 1) if t is not None else None
                if key is None or known(key) or (t & 0xFFFF) < 0x8000 or depth > 6:
                    continue
                facts[key] = (None, None)  # in progress: breaks recursion cycles
                em, ex = analyze_function_exit_mx(decode(*key, depth + 1), facts)
                if em is not None and ex is not None:
                    facts[key] = (em, ex)
                    learned = True
            if not learned:
                return graph
        return graph

    return decode


READS = {0xAD, 0xBD, 0xB9, 0xAF, 0xBF, 0xAE, 0xBE, 0xAC, 0xBC, 0xCD, 0xDD, 0xD9,
         0xCF, 0xDF, 0x6D, 0x7D, 0x79, 0x6F, 0x7F, 0xED, 0xFD, 0xF9, 0xEF, 0xFF,
         0x2D, 0x3D, 0x39, 0x2F, 0x3F, 0x0D, 0x1D, 0x19, 0x0F, 0x1F, 0x4D, 0x5D,
         0x59, 0x4F, 0x5F, 0x2C, 0x3C, 0xEC, 0xCC}


def data_reads(rom, seen):
    """ROM bytes that decoded code reads as data: (long-read offsets,
    absolute-read offsets). Long reads name their bank, so any overlap is
    data. Absolute reads go through DB, which is often WRAM here ($8168,Y in
    bank $82 code reads $7E:8168), so they only veto a candidate that starts
    at the address, the way the $88B2 mode table is read."""
    longs, absolutes = set(), set()
    for off, variants in seen.items():
        if rom[off] in READS and off + 3 < len(rom):
            length = max(v[0] for v in variants)
            a = rom[off + 1] | rom[off + 2] << 8
            bank = rom[off + 3] if length == 4 else 0x80 | off // 0x8000
            if a >= 0x8000 and (bank & 0x7F) < 0x40:
                (longs if length == 4 else absolutes).add(lorom_offset(bank << 16 | a))
    return longs, absolutes


class Own:
    """A decode graph restricted to the instructions a dead routine owns."""
    def __init__(self, graph, offsets):
        self.insns = {k: d for k, d in graph.insns.items()
                      if lorom_offset(d.key.pc & 0xFFFFFF) in offsets}


def table_entry_widths(rom, seen, declared):
    """{entry offset: (m, x)} for undeclared JMP/JSR (abs,X) tables in decoded
    code: words into the site's bank, ending where the first handler begins."""
    out = {}
    for off in sorted(seen):
        if rom[off] not in (0x7C, 0xFC) or off in declared or off // 0x8000 not in CODE_BANKS:
            continue
        m, x = next(iter(seen[off]))[1:]
        bank = 0x80 | off // 0x8000
        base = lorom_offset(bank << 16 | rom[off + 1] | rom[off + 2] << 8)
        limit = base + 64
        while base + 1 < limit:
            w = rom[base] | rom[base + 1] << 8
            if w < 0x8000:
                break
            e = lorom_offset(bank << 16 | w)
            out.setdefault(e, (m, x))
            if e > base:
                limit = min(limit, e)
            base += 2
    return out


def find_dead_code(rom, decode, seen, record, declared, blocked, forced):
    """Unreferenced routines inside the code banks' gaps.

    A gap entry (first byte after decoded code) is accepted as code only if
    its static decode is a closed, clean routine: no BRK/COP/WDM/STP/WAI,
    every byte in uncovered ROM, every call landing on a known instruction
    start (or on another routine accepted the same way), and real evidence
    (an I/O register access or a call into known code). Data rarely survives
    all of that; what does is reviewed via the generated listing."""
    covered = set()
    for off, variants in seen.items():
        covered.update(range(off, off + max(v[0] for v in variants)))
    starts = set(seen)
    accepted = 0
    # Exotic opcodes the compiled (route-verified) code never uses: data
    # decoded as code is full of stack-relative and (dp,X) forms; this
    # game's real code is not. (Ordinary forms like STA dp,X just happen to
    # be unused on the routes, so only the exotic modes count.)
    used = {rom[off] for off, v in seen.items() if "aot" in v.values()}
    exotic = {op for op in range(256) if op not in used and
              MODE_OF[op] in ("sr", "sriy", "dpxi")}
    data_refs, table_starts = data_reads(rom, seen)
    data_refs |= blocked

    def widths_before(off):
        for k in range(off - 1, off - 5, -1):
            if k in seen:
                return next(iter(seen[k]))[1:]
        return (1, 0)

    def table_entries(d):
        """Targets of a JSR/JMP (abs,X) table in dead code: consecutive words
        into the same bank's ROM half, up to the first byte already known."""
        pc = d.key.pc & 0xFFFFFF
        base = lorom_offset((pc & 0xFF0000) | d.insn.operand)
        out = []
        limit = len(rom)  # a table ends where the first handler it names begins
        while base + 1 < limit and base not in covered and base + 1 not in covered:
            w = rom[base] | rom[base + 1] << 8
            if w < 0x8000:
                break
            out.append(((pc & 0xFF0000) | w, base))
            if lorom_offset((pc & 0xFF0000) | w) > base:
                limit = min(limit, lorom_offset((pc & 0xFF0000) | w))
            base += 2
        return out

    trace = int(os.environ.get("DEAD_TRACE", "0"), 16)

    def why(code, pc24, detail=""):
        if trace and (pc24 & 0x7FFFFF) == (trace & 0x7FFFFF):
            print(f"dead: {pc24:06X} rejected at check {code} {detail}", file=sys.stderr)
        return False

    def attempt(pc24, m, x, stack, need_evidence=True):
        off = lorom_offset(pc24)
        if off in starts:
            return True
        if forced.get(off, (m, x)) != (m, x):
            return why(12, pc24)  # a jump table names this entry at other widths
        if off in covered or pc24 in stack or len(stack) > 8:
            return why(1, pc24)
        graph = decode(pc24, m, x)
        mine, evidence, calls, tables = set(), not need_evidence, [], []
        kinds = set() if need_evidence else {"callee"}
        for d in graph.insns.values():
            pc = d.key.pc & 0xFFFFFF
            o = lorom_offset(pc)
            if d.insn.mnem in BAD or (pc & 0xFFFF) < 0x8000 or o // 0x8000 not in CODE_BANKS:
                return why(2, pc24)
            span = range(o, o + d.insn.length)
            if o in starts and o not in mine:
                if d.insn.length not in {v[0] for v in seen.get(o, {(d.insn.length,): 0})}:
                    return why(7, pc24)
                if o in seen and (d.key.m & 1, d.key.x & 1) not in {v[1:] for v in seen[o]}:
                    return why(13, pc24)  # joins known code at widths it never runs at
                evidence = True  # flows into known code at an instruction start: a join
                kinds.add("join")
                continue
            if covered.intersection(span) or mine.intersection(span) and o not in mine:
                return why(3, pc24, f"{pc:06X} len {d.insn.length} m{d.key.m}x{d.key.x}")
            mine.update(span)
            if not d.successors and d.insn.mnem not in ("RTS", "RTL", "RTI", "JMP", "JML", "BRA", "BRL", "JSR"):
                return why(4, pc24)  # decode stopped somewhere unexplained
            if MODE_STR[d.insn.mode] in ("abs", "abs,x", "abs,y") and (0x2100 <= d.insn.operand < 0x2200 or
                                                        0x4200 <= d.insn.operand < 0x4400):
                evidence = True
                kinds.add("io")
            t = call_target(d)
            if t is not None:
                calls.append((t, d.key.m & 1, d.key.x & 1))
            if d.insn.mnem in ("JSR", "JMP") and MODE_STR[d.insn.mode] == "(abs,x)":
                tables.append(d)
        own = sum(1 for d in graph.insns.values() if lorom_offset(d.key.pc & 0xFFFFFF) in mine)
        if sum(rom[o] in exotic for o in own_starts_of(graph, mine)) >= 2:
            return why(11, pc24)
        if looks_like_table(rom, graph, mine):
            return why(10, pc24)
        if data_refs.intersection(mine) or off in table_starts:
            return why(9, pc24)  # known code reads these bytes as data
        if TEXT.search(bytes(rom[o] for o in sorted(mine))):
            return why(8, pc24)  # the game's strings: lowercase with '_' for spaces
        if own < 4 and need_evidence and not calls:
            return why(5, pc24)
        # Tentatively claim this body so mutually recursive callees see it.
        covered.update(mine)
        own_starts = {lorom_offset(d.key.pc & 0xFFFFFF) for d in graph.insns.values()} & mine
        starts.update(own_starts)
        ok = True
        for t, cm, cx in calls:
            to = lorom_offset(t) if (t & 0xFFFF) >= 0x8000 else None
            if to is None or to in mine:
                continue  # RAM routine (e.g. the $0199 trampoline) or local
            if to in starts:
                evidence = True
                kinds.add("call")
            elif not attempt(t, cm, cx, stack | {pc24}, need_evidence=False):
                ok = False
                break
        for d in tables if ok else ():
            for t, base in table_entries(d):
                blocked = {base, base + 1}
                if not attempt(t, d.key.m & 1, d.key.x & 1, stack | {pc24}, need_evidence=False):
                    break
                covered.update(blocked)
                mine.update(blocked)  # rolled back with the body if a parent fails
                evidence = True
        if not ok or not evidence:
            covered.difference_update(mine)
            starts.difference_update(own_starts)
            return why(6, pc24)
        txn.append((graph, mine, own_starts))
        log.append({"entry": f"{pc24:06X}", "m": m, "x": x, "own": len(own_starts),
                    "evidence": sorted(kinds), "depth": len(stack)})
        return True

    def top(pc24, m, x, need_evidence=True):
        """Accept a candidate with its whole call tree, or none of it."""
        nonlocal accepted
        txn.clear()
        mark = len(log)
        if attempt(pc24, m, x, frozenset(), need_evidence):
            for graph, _, own_starts in txn:
                record(Own(graph, own_starts), "dead")  # joined known code keeps its decode
                accepted += len(own_starts)
            return True
        del log[mark:]
        for graph, mine, own_starts in txn:  # a callee was claimed under a failed parent
            covered.difference_update(mine)
            starts.difference_update(own_starts)
        return False

    txn = []
    log = []

    def sandwiched(off):
        """A small evidence-free routine wedged between known code."""
        for mm, xx in ((1, 0), (0, 0), (1, 1), (0, 1)):
            pc24 = 0x800000 | (off // 0x8000) << 16 | 0x8000 | (off & 0x7FFF)
            graph = decode(pc24, mm, xx)
            end = max(lorom_offset(d.key.pc & 0xFFFFFF) + d.insn.length for d in graph.insns.values())
            if end in starts and top(pc24, mm, xx, need_evidence=False):
                log[-1]["evidence"] = ["sandwiched"]
                return True
        return False

    for line in (ROOT / "tools" / "decomp" / "code_hints.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            pc, m, x = line.split()[:3]
            if not top(int(pc, 16), int(m), int(x), need_evidence=False):
                raise SystemExit(f"code hint {pc} does not decode as clean code")
            log[-1]["evidence"] = ["hint"]

    # Undeclared (abs,X) jump tables in known code: each entry is code.
    for off in sorted(starts):
        if rom[off] in (0x7C, 0xFC) and off // 0x8000 in CODE_BANKS and off not in declared:
            pc24 = 0x800000 | (off // 0x8000) << 16 | 0x8000 | (off & 0x7FFF)
            base = lorom_offset((pc24 & 0xFF0000) | rom[off + 1] | rom[off + 2] << 8)
            m, x = next(iter(seen[off]))[1:]
            limit = len(rom)  # a table ends where the first handler it names begins
            while base + 1 < limit and base not in covered and base + 1 not in covered:
                w = rom[base] | rom[base + 1] << 8
                if w < 0x8000 or not top((pc24 & 0xFF0000) | w, m, x, need_evidence=False):
                    break
                if log and log[-1]["entry"] == f"{(pc24 & 0xFF0000) | w:06X}":
                    log[-1]["evidence"] = [f"table@{pc24:06X}"]
                covered.update((base, base + 1))
                target = lorom_offset((pc24 & 0xFF0000) | w)
                if target > base:
                    limit = min(limit, target)
                base += 2

    progress = True
    while progress:
        progress = False
        for bank in CODE_BANKS:
            for off in reversed(range(bank * 0x8000, bank * 0x8000 + 0x8000)):
                if off in covered:
                    continue
                gap_start = off - 1 in covered
                if not gap_start and rom[off - 1] not in (0x60, 0x6B):
                    continue  # inside a gap: only right after an RTS/RTL byte
                pc24 = 0x800000 | bank << 16 | 0x8000 | (off & 0x7FFF)
                m, x = widths_before(off)
                for mm, xx in dict.fromkeys([forced.get(off, (m, x)), (1, 0), (0, 0), (1, 1), (0, 1)]):
                    if top(pc24, mm, xx):
                        progress = True
                        break
                else:
                    progress |= sandwiched(off)
    return accepted, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("out")
    ap.add_argument("--profiles", action="append", default=[])
    args = ap.parse_args()

    emitter = importlib.import_module("v2.emit_function")
    original = emitter.decode_function
    seen = {}


    votes = collections.Counter()  # compiled graphs containing each decode

    def record(graph, source, into=None):
        into = seen if into is None else into
        for d in graph.insns.values():
            pc24 = d.key.pc & 0xFFFFFF
            if (pc24 & 0xFFFF) < 0x8000 or ((pc24 >> 16) & 0x7F) >= 0x7E:
                continue
            ins = d.insn
            key = (ins.length, int(ins.m_flag) & 1, int(ins.x_flag) & 1)
            into.setdefault(lorom_offset(pc24), {}).setdefault(key, source)
            if source == "aot":
                votes[lorom_offset(pc24), key] += 1

    def observe(rom, bank, start, entry_m, entry_x, **kwargs):
        graph = original(rom, bank, start, entry_m, entry_x, **kwargs)
        record(graph, "aot")
        roms.append(rom)
        return graph

    roms = []
    emitter.decode_function = observe
    seeds = []
    dirs = sorted(args.profiles, key=lambda p: [int(t) if t.isdigit() else t
                                                 for t in __import__("re").split(r"(\d+)", p)])
    for i, d in enumerate(dirs):
        flag = "--profile-manifest" if i == len(dirs) - 1 else "--historical-profile-manifest"
        for f in sorted(pathlib.Path(d).glob("*.json*")):
            seeds += [flag, str(f)]
    os.environ["SNESRECOMP_JOBS"] = "1"  # pool workers would observe in their own process
    with tempfile.TemporaryDirectory() as tmp:
        argv = sys.argv
        sys.argv = ["v2_emit", "--rom", args.rom, "--cfg-dir", str(ROOT / "recomp"),
                    "--out-dir", os.path.join(tmp, "gen"), "--cfg-roots"] + seeds
        try:
            import v2_emit
            rc = v2_emit.main()
        finally:
            sys.argv = argv
            emitter.decode_function = original
        if rc:
            raise SystemExit(f"v2_emit failed: {rc}")
        tmp_gen = os.path.join(tmp, "gen")
        manifest_text = (pathlib.Path(tmp_gen) / "program_manifest.json").read_text()

    # Static pass: code the recomp leaves to the interpreter (LLE-only
    # variants, off-route callees) is still code. Decode every LLE-only
    # manifest node and every static call/jump target that lands outside the
    # compiled set, at the caller's widths, to a fixpoint. Compiled ("aot")
    # decodes win any overlap; static ones only fill gaps.
    rom = roms[0]
    decode = exit_aware_decoder(rom, json.loads(manifest_text))
    manifest = json.loads(manifest_text)["nodes"]
    pending = [(int(k[:6], 16), int(k[8]), int(k[10])) for k, v in manifest.items()
               if v["disposition"] == "lle_only"]
    declared = set()
    for cfg in sorted((ROOT / "recomp").glob("bank*.cfg")):
        bank = int(cfg.stem[4:], 16)
        for line in cfg.read_text().splitlines():
            if line.startswith("indirect_dispatch") and "targets:" in line:
                site = lorom_offset(bank << 16 | int(line.split()[1], 16))
                declared.add(site)
                m, x = next(iter(seen.get(site, {(0, 1, 0): 0})))[1:]
                pending += [(int(t, 16), m, x) for t in line.split("targets:")[1].split()[0].split(",")]
    done = set()
    while pending:
        pc24, m, x = pending.pop()
        if (pc24, m, x) in done or (pc24 & 0xFFFF) < 0x8000 or ((pc24 >> 16) & 0x7F) >= 0x7E:
            continue
        done.add((pc24, m, x))
        graph = decode(pc24, m, x)
        record(graph, "static")
        for d in graph.insns.values():
            ins, pc = d.insn, d.key.pc & 0xFFFFFF
            if ins.mnem in ("JSR", "JMP") and MODE_STR[ins.mode] == "abs" or ins.mnem in ("JSL", "JML") and ins.length == 4:
                t = ins.operand if ins.length == 4 else (pc & 0xFF0000) | ins.operand
                if lorom_offset(t) not in seen:
                    pending.append((t, d.key.m & 1, d.key.x & 1))

    # Dead code can reveal tables (lda.l $83C89A,x in a recovered routine)
    # that an earlier acceptance decoded as code: rerun with those bytes
    # blocked until no recovered code covers bytes that code reads as data.
    # Likewise a jump table in recovered code fixes its entries' widths
    # (SEP #$30 / JSR ($81FF,X) enters every handler with 8-bit A and X).
    blocked, forced = set(), {}
    while True:
        trial = {off: dict(v) for off, v in seen.items()}
        dead, dead_log = find_dead_code(rom, decode, trial, lambda g, src: record(g, src, trial),
                                        declared, blocked, forced)
        dead_bytes = {off + n for off, v in trial.items() if "dead" in v.values()
                      for n in range(max(x[0] for x in v))}
        clash = (data_reads(rom, trial)[0] & dead_bytes) - blocked
        widths = {e: mx for e, mx in table_entry_widths(rom, trial, declared).items()
                  if e in trial and "dead" in trial[e].values()
                  and mx not in {v[1:] for v in trial[e]} and e not in forced}
        if not clash and not widths:
            seen = trial
            break
        blocked |= clash
        forced.update(widths)
    pathlib.Path(args.out).with_name("dead.json").write_text(json.dumps(dead_log, indent=0))

    # Compiled variants can disagree where a callee has a multi-mode exit
    # (the recomp forks by runtime width): the listing takes the decode most
    # compiled graphs agree on and reports the minority.
    insns, conflicts, minority, static = {}, {}, {}, 0
    for off, variants in sorted(seen.items()):
        lengths = {v[0] for v in variants}
        aot = sorted((v for v, src in variants.items() if src == "aot"),
                     key=lambda v: (-votes[off, v], v))
        if len(lengths) > 1 and not aot:
            conflicts[str(off)] = sorted(variants)
            continue
        if len({v[0] for v in aot}) > 1:
            if votes[off, aot[0]] == votes[off, aot[1]]:
                conflicts[str(off)] = sorted(variants)
                continue
            minority[str(off)] = [v for v in aot if v[0] != aot[0][0]]
        best = aot[0] if aot else sorted(variants)[0]
        insns[str(off)] = [*best, variants[best]]
        static += not aot
    pathlib.Path(args.out).write_text(json.dumps({"insns": insns, "conflicts": conflicts,
                                                  "minority": minority}))
    print(f"{len(insns)} instructions ({static} static-only, {dead} dead-code), "
          f"{len(conflicts)} conflicting offsets, {len(minority)} minority decodes")


if __name__ == "__main__":
    main()
