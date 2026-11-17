"""Synthetic-only P0 negatives; no native build, timestep or P3 dispatch."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / 'ci/guards/issue633_new_only_p0_p2.py'
spec = spec_from_file_location('issue633_new_only_p0_p2', FILE)
module = module_from_spec(spec)
spec.loader.exec_module(module)

DECK = '''[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = e
          fvm_species = 'O2p Om Op'
          fem_potential = potential
        []
      []
    []
  []
[]
'''
JSON = {'species': {s: {'initial_number_density': 1e14,
                        'transport_coef': 'functor'} for s in ('e','O2p','Om','Op')}}


def layers(deck=DECK):
    return {'migrated_continuity.i': deck, **{f'layer_{i}.i': '# other source\n' for i in range(10)}}


def test_no_native_and_no_runtime_claim():
    result = module.inspect(layers(), JSON, '417')
    assert result['status'] == 'P0_INPUT_ONLY_PASS'
    assert result['generated_fv_kernels'] == 'NOT_VERIFIED'
    assert result['P3'] == 'NOT_RUN'


@pytest.mark.parametrize('state', ('log_O2p','log_Om','log_Op','log_ni','log_nm','log_nop'))
@pytest.mark.parametrize('section', ('FVKernels','FVBCs'))
def test_old_or_new_native_names_fail(state, section):
    extra = f'\n[{section}]\n  [arbitrary_legacy]\n    type = SomeOldType\n    variable = {state}\n  []\n[]\n'
    with pytest.raises(module.GateError, match='NATIVE_FV_ION_OWNER_PRESENT_1'):
        module.inspect(layers(DECK+extra), JSON, '417')


def test_missing_or_duplicate_selection_fails():
    with pytest.raises(module.GateError, match='CONTINUITY_COUNT:2'):
        module.inspect(layers(DECK+DECK), JSON, '417')
    with pytest.raises(module.GateError, match='NEW_ONLY_SPECIES_SELECTION_MISMATCH'):
        module.inspect(layers(DECK.replace('O2p Om Op', 'O2p Om Om')), JSON, '417')


def test_missing_density_and_missing_potential_fail():
    bad = {'species': {**JSON['species'], 'Om': {'initial_number_density': float('nan'), 'transport_coef': 'functor'}}}
    with pytest.raises(module.GateError, match='JSON_INITIAL_DENSITY_INVALID:Om'):
        module.inspect(layers(), bad, '941')
    with pytest.raises(module.GateError, match='EXPLICIT_POTENTIAL_REQUIRED'):
        module.inspect(layers(DECK.replace('fem_potential = potential','')), JSON, '941')


def test_unresolved_input_and_manual_flag_fail():
    with pytest.raises(module.GateError, match='UNRESOLVED_INCLUDE'):
        module.inspect(layers(DECK+'!include existing.i\n'), JSON, '417')
    with pytest.raises(module.GateError, match='MANUAL_OWNER_FLAG_FORBIDDEN'):
        module.inspect(layers(DECK.replace('fem_potential = potential','fem_potential = potential\n          fvm_kernel_ownership = physics')), JSON, '417')


def test_inactive_manual_template_has_no_auto_trigger():
    text = (ROOT/'ci/workflow_templates/issue633-new-only-400w-100us-manual.DRAFT.yml').read_text()
    assert 'workflow_dispatch:' in text
    assert 'ISSUE633_NEW_ONLY_400W_100US_BOTH_CASES_APPROVED' in text
    assert 'case: [\'417\', \'941\']' in text
    assert 'SCIENCE_HOLD' in text
    for trigger in ('\n  push:', '\n  pull_request:', '\n  schedule:', '\n  repository_dispatch:'):
        assert trigger not in text
    assert not (ROOT/'.github/workflows/issue633-new-only-400w-100us.yml').exists()
