import csv
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from experiments.Issue27_surface_reactions.controlled_wall import combined as a6
from experiments.Issue27_surface_reactions.controlled_wall import electron_wall as a7
from experiments.Issue31_r4_q0_all_ground import run as q0_run
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import stage_case

ROOT = Path('/workspace')
OUT = ROOT / 'issue197-h3-results'
CASES = OUT / 'cases'
LOGS = OUT / 'logs'
SOURCE = ROOT / 'experiments/Issue1_reactor_o2plus_integration/migration_only_exact_phi_ic'
EXE = ROOT / 'physics_app/physics-opt'
CASES.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)
(OUT / 'driver_state.json').write_text(json.dumps({'status': 'STARTED'}, indent=2) + '\n')

REL_FLUX_TOL = 1.0e-3
REL_BALANCE_TOL = 1.0e-8
ZERO_FLUX_ABS_TOL = 1.0e-20
FIELD_MAGNITUDE = 2.0e4


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def top_float(text, name):
    match = re.search(rf'(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)', text)
    if not match:
        raise RuntimeError(f'missing scalar {name}')
    return float(match.group(1).strip())


def replace_scalar(text, name, value):
    updated, count = re.subn(
        rf'(?m)^{re.escape(name)}\s*=\s*.*$',
        f'{name} = {value}',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f'failed to replace scalar {name}')
    return updated


def rel_err(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1.0e-300)


def build_a7_ownership_surface():
    spec = json.loads(
        (ROOT / 'experiments/Issue27_surface_reactions/A7_comsol_electron_wall/experiment.json').read_text()
    )
    params = spec['parameters']
    base = (ROOT / 'experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i').read_text()
    text, meta = a6._build_a6_case_input(
        base,
        parameters=a7._a6_parameters(params),
        mode='comsol_wall',
    )
    return text, meta


def audit_a7_ownership(text, meta):
    failures = []
    preflight = a6._a5_preflight(text, meta)
    if preflight['status'] != 'PASS':
        failures.extend(preflight['failures'])
    if not preflight['charged_interior_wall_double_counting_avoided']:
        failures.append('bulk electrostatic drift reaches a physical wall')

    for species, cfg in a6.CHARGED.items():
        material = f'FunctorMaterials/issue27_a6_{species}_wall_flux'
        if mp.get_parameter(text, material, 'type') != 'QPXIonWallFluxMaterial':
            failures.append(f'{species}: unexpected wall material type')
        if mp.get_parameter(text, material, 'potential') != 'potential_plasma':
            failures.append(f'{species}: potential is not potential_plasma')
        if mp.get_parameter(text, material, 'mobility') != cfg['mobility']:
            failures.append(f'{species}: mobility owner mismatch')
        if int(float(mp.get_parameter(text, material, 'charge_number'))) != int(cfg['charge']):
            failures.append(f'{species}: charge number mismatch')
        if not math.isclose(
            float(mp.get_parameter(text, material, 'molar_mass')),
            float(cfg['molar_mass']),
            rel_tol=1.0e-15,
            abs_tol=0.0,
        ):
            failures.append(f'{species}: molar mass mismatch')
        if mp.get_parameter(text, material, 'declare_suffix') != species:
            failures.append(f'{species}: suffix/ownership mismatch')

        for wall in a6.PLASMA_WALLS:
            surface_bc, migration_bc, _, _ = a6._charged_names(species, wall)
            for kind, bc in [('surface', surface_bc), ('migration', migration_bc)]:
                path = f'FVBCs/{bc}'
                if mp.get_parameter(text, path, 'boundary') != wall:
                    failures.append(f'{species}/{wall}/{kind}: boundary mismatch')
                if not math.isclose(float(mp.get_parameter(text, path, 'factor')), -1.0):
                    failures.append(f'{species}/{wall}/{kind}: factor mismatch')
            if mp.get_parameter(text, f'FVBCs/{surface_bc}', 'functor') != f'ion_surface_mass_flux_{species}':
                failures.append(f'{species}/{wall}: surface functor ownership mismatch')
            if mp.get_parameter(text, f'FVBCs/{migration_bc}', 'functor') != f'ion_migration_mass_flux_{species}':
                failures.append(f'{species}/{wall}: migration functor ownership mismatch')

    return {
        'status': 'PASS' if not failures else 'FAIL',
        'failures': failures,
        'a5_preflight': preflight,
        'charged_species': sorted(a6.CHARGED),
        'plasma_walls': list(a6.PLASMA_WALLS),
        'expected_surface_bc_count': len(a6.CHARGED) * len(a6.PLASMA_WALLS),
        'expected_migration_bc_count': len(a6.CHARGED) * len(a6.PLASMA_WALLS),
    }


def current_runtime_input(*, charge_number, field_sign):
    text = (SOURCE / 'migration_only_exact_phi_ic.i').read_text()
    text = replace_scalar(text, 'z_i', int(charge_number))
    if field_sign > 0:
        text = replace_scalar(text, 'phi_left', 20000)
        text = replace_scalar(text, 'phi_right', 0)
        text = mp.upsert_parameter(text, 'Functions/phi_exact', 'expression', "'20000*(1-x)'")
    else:
        text = replace_scalar(text, 'phi_left', 0)
        text = replace_scalar(text, 'phi_right', 20000)
        text = mp.upsert_parameter(text, 'Functions/phi_exact', 'expression', "'20000*x'")

    replacements = {
        'FunctorMaterials/ion_wall_flux': 'PhysicsIonWallFluxMaterial',
        'FVKernels/ion_time': 'PhysicsFVMassFractionTimeDerivative',
        'FVKernels/ion_electrostatic_drift': 'PhysicsFVElectrostaticDrift',
    }
    for path, object_type in replacements.items():
        text = mp.upsert_parameter(text, path, 'type', object_type)
    text = mp.upsert_parameter(text, 'Executioner', 'end_time', '1.0e-5')
    text = mp.upsert_parameter(text, 'Executioner', 'nl_rel_tol', '1.0e-16')
    return text, replacements


def run_control(name, *, charge_number, field_sign):
    text, replacements = current_runtime_input(
        charge_number=charge_number,
        field_sign=field_sign,
    )
    target = CASES / name
    staged = stage_case(
        SOURCE,
        target,
        input_text=text,
        purge_directory_names=('.jitcache', 'checkpoint', 'checkpoints'),
        purge_patterns=('input_out*', '*.log', '*.e', '*.exo'),
    )
    item = {
        'charge_number': charge_number,
        'field_sign': field_sign,
        'object_promotions': replacements,
        'staging': staged,
        'input_sha256': sha256(target / 'input.i'),
    }
    p2 = q0_run._p2(EXE, target, LOGS / f'{name}_p2.log', 300.0)
    item['p2'] = p2
    if p2['returncode'] != 0:
        item['classification'] = 'NOT_EVALUATED_P2_FAILURE'
        return item
    runtime = q0_run._runtime(EXE, target, LOGS / f'{name}_runtime.log', 300.0)
    item['runtime'] = runtime
    csv_path = target / 'input_out.csv'
    if runtime['returncode'] != 0 or not csv_path.is_file():
        item['classification'] = 'NOT_EVALUATED_RUNTIME_FAILURE'
        return item
    with csv_path.open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        item['classification'] = 'INCOMPLETE_TIMELINE'
        return item
    r0 = min(rows, key=lambda row: abs(float(row['time'])))
    positives = [row for row in rows if float(row['time']) > 0.0]
    if not positives:
        item['classification'] = 'INCOMPLETE_TIMELINE'
        return item
    r1 = positives[0]

    rho0 = top_float(text, 'rho0')
    w0 = 1.0e-6
    mu = top_float(text, 'mu_i')
    expected_active_initial = rho0 * w0 * mu * FIELD_MAGNITUDE
    active_wall = 'right' if charge_number * field_sign > 0 else 'left'
    inactive_wall = 'left' if active_wall == 'right' else 'right'

    initial = {
        'left': float(r0['left_migration_mass_loss_rate']),
        'right': float(r0['right_migration_mass_loss_rate']),
        'surface_left': float(r0['left_surface_mass_loss_rate']),
        'surface_right': float(r0['right_surface_mass_loss_rate']),
    }
    final = {
        'left': float(r1['left_migration_mass_loss_rate']),
        'right': float(r1['right_migration_mass_loss_rate']),
        'surface_left': float(r1['left_surface_mass_loss_rate']),
        'surface_right': float(r1['right_surface_mass_loss_rate']),
    }
    dt = float(r1['time']) - float(r0['time'])
    dm = float(r1['ion_mass_inventory']) - float(r0['ion_mass_inventory'])
    final_migration = final['left'] + final['right']
    initial_active = initial[active_wall]
    initial_inactive = initial[inactive_wall]
    checks = {
        'initial_active_direction': initial_active > 0.0,
        'initial_inactive_clamped': abs(initial_inactive) <= ZERO_FLUX_ABS_TOL,
        'initial_active_magnitude': rel_err(initial_active, expected_active_initial) <= REL_FLUX_TOL,
        'surface_zero_initial': abs(initial['surface_left']) <= ZERO_FLUX_ABS_TOL and abs(initial['surface_right']) <= ZERO_FLUX_ABS_TOL,
        'surface_zero_final': abs(final['surface_left']) <= ZERO_FLUX_ABS_TOL and abs(final['surface_right']) <= ZERO_FLUX_ABS_TOL,
        'final_direction': final[active_wall] > 0.0 and abs(final[inactive_wall]) <= ZERO_FLUX_ABS_TOL,
        'one_step_mass_balance': rel_err(dm, -final_migration * dt) <= REL_BALANCE_TOL,
    }
    item.update({
        'classification': 'MEASURED',
        'csv_sha256': sha256(csv_path),
        'active_wall': active_wall,
        'expected_initial_active_flux_kg_m2_s': expected_active_initial,
        'initial': initial,
        'final': final,
        'dt_s': dt,
        'mass_change_kg_m2': dm,
        'mass_balance_relative_error': rel_err(dm, -final_migration * dt),
        'checks': checks,
        'pass': all(checks.values()),
    })
    return item


a7_text, a7_meta = build_a7_ownership_surface()
ownership = audit_a7_ownership(a7_text, a7_meta)
mutated = mp.upsert_parameter(
    a7_text,
    'FunctorMaterials/issue27_a6_Om_wall_flux',
    'charge_number',
    '1',
)
negative_mutation = audit_a7_ownership(mutated, a7_meta)
negative_control_detected = (
    negative_mutation['status'] == 'FAIL'
    and any('Om: charge number mismatch' in x for x in negative_mutation['failures'])
)

controls = {}
for name, z, field_sign in (
    ('positive_charge_positive_field', 1, 1),
    ('positive_charge_negative_field', 1, -1),
    ('negative_charge_positive_field', -1, 1),
    ('negative_charge_negative_field', -1, -1),
):
    controls[name] = run_control(name, charge_number=z, field_sign=field_sign)

scientific_ready = all(item.get('classification') == 'MEASURED' for item in controls.values())
runtime_pass = scientific_ready and all(item.get('pass') is True for item in controls.values())
summary = {
    'controller': 194,
    'hypothesis_owner': 197,
    'repository_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'executable_sha256': sha256(EXE),
    'diagnostic': 'charged-heavy migration sign/clamp/ownership audit',
    'physics_semantics_changed': False,
    'ownership_audit': ownership,
    'negative_sign_mutation': {
        'detected': negative_control_detected,
        'audit_status': negative_mutation['status'],
        'failures': negative_mutation['failures'],
    },
    'runtime_controls': controls,
    'status': 'RUNNING',
}
if ownership['status'] == 'PASS' and negative_control_detected and runtime_pass:
    summary['status'] = 'H3_MIGRATION_AUDIT_PASS'
elif not scientific_ready:
    summary['status'] = 'H3_MIGRATION_AUDIT_NOT_EVALUATED'
else:
    summary['status'] = 'H3_MIGRATION_AUDIT_FAIL'

fingerprint = hashlib.sha256()
fingerprint.update(summary['repository_head'].encode())
fingerprint.update(summary['executable_sha256'].encode())
for name in sorted(controls):
    item = controls[name]
    fingerprint.update(name.encode())
    fingerprint.update(item.get('input_sha256', '').encode())
    fingerprint.update(item.get('csv_sha256', '').encode())
summary['evidence_identity'] = (
    f"issue197-h3-migration-{summary['repository_head'][:12]}-{fingerprint.hexdigest()[:16]}"
)
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
(OUT / 'driver_state.json').write_text(
    json.dumps({'status': summary['status'], 'evidence_identity': summary['evidence_identity']}, indent=2, sort_keys=True) + '\n'
)
print(json.dumps(summary, indent=2, sort_keys=True))

if summary['status'] == 'H3_MIGRATION_AUDIT_PASS':
    raise SystemExit(0)
if summary['status'] == 'H3_MIGRATION_AUDIT_NOT_EVALUATED':
    raise SystemExit(2)
raise SystemExit(1)
