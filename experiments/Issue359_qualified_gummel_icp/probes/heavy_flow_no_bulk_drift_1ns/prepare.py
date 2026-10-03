#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from experiments.Issue359_qualified_gummel_icp import run as issue359
from experiments.Issue359_qualified_gummel_icp import heavy_continuity as hc
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

DT = 1.0e-9
ALL_B = {
    'inlet', 'outlet', 'plasma_electrode', 'plasma_metal',
    'plasma_right', 'plasma_cover', 'plasma_wafer', 'plasma_focus_ring'
}


def set_one_step(text: str) -> str:
    for key, value in (
        ('dt', f'{DT:.17g}'),
        ('end_time', f'{DT:.17g}'),
        ('num_steps', '1'),
    ):
        text = mp.upsert_parameter(text, 'Executioner', key, value)
    if mp.get_parameter(text, 'Executioner', 'dtmin') is not None:
        text = mp.upsert_parameter(text, 'Executioner', 'dtmin', f'{DT:.17g}')
    if mp.get_parameter(text, 'Executioner', 'dtmax') is not None:
        text = mp.upsert_parameter(text, 'Executioner', 'dtmax', f'{DT:.17g}')
    return text


def remove_block_if_present(text: str, path: str) -> str:
    return mb.remove_block(text, path) if mb.has_block(text, path) else text


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit('usage: prepare.py <case-dir>')
    case = Path(sys.argv[1]).resolve()
    if case.exists():
        shutil.rmtree(case)

    # Start from the exact current Issue359 frozen bundle so flow, geometry,
    # surface chemistry, electron state, and all-ground Poisson policy are reused.
    issue359._stage(
        case,
        electron_substeps=1,
        heavy_steps=1,
        write_exodus=True,
    )

    paths = {
        'outer': case / 'input.i',
        'driver': case / 'gummel_driver.i',
        'electron': case / 'electron_sub.i',
        'poisson': case / 'poisson_sub.i',
    }
    text = {name: path.read_text() for name, path in paths.items()}

    # Bulk electrostatic drift OFF for this discriminator.
    for species in hc.CHARGED_HEAVY:
        text['outer'] = remove_block_if_present(
            text['outer'], f'FVKernels/{species}_electrostatic_drift'
        )
    for species in hc.SOLVED_HEAVY:
        text['outer'] = remove_block_if_present(
            text['outer'], f'FVKernels/{species}_heavy_mass_em_correction'
        )
    for block in ('FVKernels/electron_drift', 'FVKernels/energy_drift'):
        text['electron'] = remove_block_if_present(text['electron'], block)

    # Keep the accepted surface-reaction / wall-flux contract unchanged.
    # This intentionally does not rewrite any Issue27-derived wall object.

    # One physical step everywhere: 1 ns.
    for name in text:
        text[name] = set_one_step(text[name])

    # Outer Exodus retained for direct morphology inspection.
    text['outer'] = mp.upsert_parameter(text['outer'], 'Outputs', 'exodus', 'true')
    text['outer'] = mp.upsert_parameter(text['outer'], 'Outputs', 'execute_on', 'FINAL')

    for name, path in paths.items():
        path.write_text(text[name])

    # Contract checks.
    outer = text['outer']
    electron = text['electron']
    poisson = text['poisson']

    checks = {}
    checks['dt_1ns_all_apps'] = all(
        abs(float(mp.get_parameter(text[name], 'Executioner', 'dt') or 'nan') - DT) < 1e-18
        and abs(float(mp.get_parameter(text[name], 'Executioner', 'end_time') or 'nan') - DT) < 1e-18
        and int(mp.get_parameter(text[name], 'Executioner', 'num_steps') or '0') == 1
        for name in text
    )
    checks['inlet_20_sccm'] = re.search(r'(?m)^Q_sccm\s*=\s*20(?:\.0+)?\s*$', outer) is not None
    checks['outlet_10_mTorr'] = re.search(
        r'(?m)^outlet_pressure\s*=\s*1\.333223684\s*$', outer
    ) is not None
    checks['poisson_all_ground'] = set(mp.words(
        mp.get_parameter(poisson, 'FVBCs/grounded_plasma_boundary', 'boundary') or ''
    )) == ALL_B

    heavy_bulk_off = []
    for species in hc.CHARGED_HEAVY:
        heavy_bulk_off.append(not mb.has_block(outer, f'FVKernels/{species}_electrostatic_drift'))
    for species in hc.SOLVED_HEAVY:
        heavy_bulk_off.append(not mb.has_block(outer, f'FVKernels/{species}_heavy_mass_em_correction'))
    checks['heavy_bulk_drift_off'] = all(heavy_bulk_off)
    checks['electron_bulk_drift_off'] = (
        not mb.has_block(electron, 'FVKernels/electron_drift')
        and not mb.has_block(electron, 'FVKernels/energy_drift')
    )

    # Representative accepted surface-reaction owners must remain present.
    required_surface = [
        'FVBCs/O_wall_loss',
        'FVBCs/O2s_wall_loss',
        'FVBCs/Os_wall_loss',
        'FunctorMaterials/O2p_wall_flux',
        'FunctorMaterials/Om_wall_flux',
        'FunctorMaterials/Op_wall_flux',
        'FVBCs/O2p_surface_plasma_electrode',
        'FVBCs/Om_surface_plasma_electrode',
        'FVBCs/Op_surface_plasma_electrode',
        'FVBCs/ion_neutralization_O_return',
    ]
    checks['surface_reaction_contract_preserved'] = all(
        mb.has_block(outer, path) for path in required_surface
    )
    checks['surface_reaction_values_preserved'] = all(
        reaction in outer or species in hc.SURFACE_REACTIONS
        for species, reaction in hc.SURFACE_REACTIONS.items()
    )

    failed = sorted(k for k, ok in checks.items() if not ok)
    contract = {
        'probe': 'heavy-flow-all-ground-no-bulk-drift-1ns',
        'dt_s': DT,
        'num_steps': 1,
        'flow_sccm': 20.0,
        'outlet_pressure_Pa': 1.333223684,
        'outlet_pressure_mTorr': 10.0,
        'all_electrostatic_boundaries_grounded': True,
        'bulk_drift': {
            'electron_particle': False,
            'electron_energy': False,
            'charged_heavy': False,
            'heavy_mass_em_correction': False,
        },
        'surface_reactions': hc.SURFACE_REACTIONS,
        'surface_sticking': hc.WALL_STICKING,
        'surface_contract_note': 'Issue359/Issue27 wall-reaction objects retained unchanged; only bulk drift kernels removed',
        'checks': checks,
        'status': 'PASS' if not failed else 'FAIL',
        'failed_checks': failed,
    }
    (case / 'probe_contract.json').write_text(json.dumps(contract, indent=2, sort_keys=True) + '\n')
    print(json.dumps(contract, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(f'probe contract failed: {failed}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
