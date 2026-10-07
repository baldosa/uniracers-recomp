import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from promote_roots import candidates, existing, entries

def disc(variant, status='candidate_requires_analysis_and_replay', hits=1, bails=0, e=0, site=None):
    pc = '0x' + variant.split(':')[0]
    return {'variant': variant, 'candidate_status': status, 'observed_hits': hits,
            'bail_hits': bails, 'emulation': e, 'site_pc24': site or '0xFFFFFF', 'target_pc24': pc}

c = candidates([
    disc('008610:M1X0', 'landing_requires_function_boundary', hits=5),
    disc('02D353:M0X0', hits=2), disc('02D353:M1X0', hits=9),   # hottest mode wins
    disc('01D86E:M1X0', bails=1),                               # bailed: skipped
    disc('03ABCD:M1X1', e=1),                                   # emulation mode: skipped
    disc('7E2000:M1X1'),                                        # WRAM code: skipped
    disc('00B5FD:M1X0', status='unsafe_target'),                # not promotable
])
assert c == {(0, 0x8610): (1, 0), (2, 0xD353): (1, 0)}, c
# frame-resume landing (site == target) counts even without hits
c = candidates([disc('0282EF:M1X0', status='no_execution_evidence', hits=0, site='0x0282EF')])
assert c == {(2, 0x82EF): (1, 0)}, c

toml = '[[func]]\nname = "I_NMI"\naddr = "8588"\nbank = 0\nemit = false\n'
have = existing(toml)
assert have == {(0, 0x8588)}
out = entries({(0, 0x8588): (1, 0), (0, 0x8610): (1, 0)}, have)
assert len(out) == 1 and 'name = "sub_008610"' in out[0] and 'entry_x = 0' in out[0]
print('ok')
