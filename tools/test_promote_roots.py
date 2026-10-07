import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from promote_roots import candidates, plan, render

def disc(variant, status='candidate_requires_analysis_and_replay', hits=1, bails=0, e=0, site=None):
    pc = '0x' + variant.split(':')[0]
    return {'variant': variant, 'candidate_status': status, 'observed_hits': hits,
            'bail_hits': bails, 'emulation': e, 'site_pc24': site or '0xFFFFFF', 'target_pc24': pc}

# candidates: every clean mode per address, with its hit count
c = candidates([
    disc('008610:M1X0', 'landing_requires_function_boundary', hits=5),
    disc('02D353:M0X0', hits=2), disc('02D353:M1X0', hits=9),
    disc('01D86E:M1X0', bails=1),                               # bailed: skipped
    disc('03ABCD:M1X1', e=1),                                   # emulation mode: skipped
    disc('7E2000:M1X1'),                                        # WRAM code: skipped
    disc('00B5FD:M1X0', status='unsafe_target'),                # not promotable
    disc('0282EF:M1X1', status='no_execution_evidence', hits=0, site='0x0282EF'),  # resume landing
])
assert c == {(0, 0x8610): {(1, 0): 5}, (2, 0xD353): {(0, 0): 2, (1, 0): 9},
             (2, 0x82EF): {(1, 1): 0}}, c

# plan: new address -> func in its hottest mode + variants for the others;
# known address -> variants for modes not yet present.
toml = ('[[func]]\nname = "I_NMI"\naddr = "8588"\nbank = 0\nemit = true\nentry_m = 1\nentry_x = 0\n'
        '[[variant]]\nbank = 0\naddr = "8588"\nentry_m = 1\nentry_x = 1\n')
funcs, variants = plan({(0, 0x8588): {(1, 0): 3, (1, 1): 1, (0, 0): 1},
                        (2, 0xD353): {(0, 0): 2, (1, 0): 9}}, toml)
assert funcs == [((2, 0xD353), (1, 0))], funcs
assert variants == [((0, 0x8588), (0, 0)), ((2, 0xD353), (0, 0))], variants
text = render(funcs, variants)
assert 'name = "sub_02D353"' in text and text.count('[[variant]]') == 2
print('ok')
