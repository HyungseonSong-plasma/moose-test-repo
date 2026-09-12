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
from experiments.Issue193_a8_see_acceptance.run import _promote_current_acceptance_types
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import stage_case

ROOT = Path('/workspace')
OUT = ROOT / 'issue194-a7-results'
CASES = OUT / 'cases'
LOGS = OUT / 'logs'
CASES.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)
SOURCE = ROOT / 'experiments/Issue91_real_qvt_r3/r3_e0'
EXE = ROOT / 'physics_app/physics-opt'
BASELINE_DT = 1.0e-10
REFINEMENT_DTS = (5.0e-11, 2.5e-11)
TARGET_END = 5.0e-10
ALL_DTS = (BASELINE_DT, *REFINEMENT_DTS)
spec = json.loads((ROOT / 'experiments/Issue27_surface_reactions/A7_comsol_electron_wall/experiment.json').read_text())
params = spec['parameters']
base_text = (SOURCE / 'heavy_base.i').read_text()


def add_pp(text, name, body):
    path = f'Postprocessors/{name}'
    if mb.has_block(text, path):
        return text
    return mb.insert_child_block(text, 'Postprocessors', f'  [{name}]\n{body}\n  []')


def instrument(text, *, dt, end_time):
    text = mp.upsert_parameter(text, 'Executioner', 'dt', f'{dt:.17g}')
    text = mp.upsert_parameter(text, 'Executioner', 'end_time', f'{end_time:.17g}')
    observed = (
        'n_e_inventory', 'n_e_min', 'n_e_max', 'n_e_avg',
        'mass_O2p', 'mass_Om', 'mass_Op',
        'r31_charge_integral', 'r31_gauss_flux_charge',
    )
    for pp in observed:
        if mb.has_block(text, f'Postprocessors/{pp}'):
            text = mp.upsert_parameter(text, f'Postprocessors/{pp}', 'execute_on', "'INITIAL TIMESTEP_END'")
    text = add_pp(text, 'issue194_rho_q_min', "    type = ADElementExtremeFunctorValue\n    functor = charge_density\n    value_type = min\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'")
    text = add_pp(text, 'issue194_rho_q_max', "    type = ADElementExtremeFunctorValue\n    functor = charge_density\n    value_type = max\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'")
    text = add_pp(text, 'issue194_phi_min', "    type = ElementExtremeValue\n    variable = potential_plasma\n    value_type = min\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'")
    text = add_pp(text, 'issue194_phi_max', "    type = ElementExtremeValue\n    variable = potential_plasma\n    value_type = max\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'")
    text = add_pp(text, 'issue194_phi_avg', "    type = ElementAverageValue\n    variable = potential_plasma\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'")
    return text


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def dt_label(dt):
    return f'{dt:.3e}'.replace('+', '').replace('-', 'm').replace('.', 'p')


def stage(name, text, meta, *, dt):
    target = CASES / name
    current_text, promotion = _promote_current_acceptance_types(
        instrument(text, dt=dt, end_time=TARGET_END)
    )
    staged = stage_case(
        SOURCE,
        target,
        input_text=current_text,
        purge_directory_names=('.jitcache', 'checkpoint', 'checkpoints'),
        purge_patterns=('input_out*', '*.log', '*.e', '*.exo', 'prepare_evidence.json'),
    )
    evidence = {
        'source_meta': meta,
        'current_physics_object_promotion': promotion,
        'diagnostic_dt_s': dt,
        'diagnostic_end_time_s': TARGET_END,
        'expected_steps': int(round(TARGET_END / dt)),
        'physics_semantics_changed': False,
    }
    (target / 'prepare_evidence.json').write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + '\n'
    )
    return {'staging': staged, 'meta': evidence}


def read_rows(csv_path):
    if not csv_path.is_file():
        return []
    with csv_path.open(newline='') as handle:
        return list(csv.DictReader(handle))


def select_row(row):
    base = {
        'time', 'domain_volume', 'n_e_inventory', 'n_e_min', 'n_e_max', 'n_e_avg',
        'mass_O2p', 'mass_Om', 'mass_Op',
        'r31_charge_integral', 'r31_gauss_flux_charge',
        'issue194_rho_q_min', 'issue194_rho_q_max',
        'issue194_phi_min', 'issue194_phi_max', 'issue194_phi_avg',
        a7.THERMAL_PP,
    }
    dynamic = {
        key for key in row
        if key.startswith('issue27_a6_')
        and key.endswith('_rate')
        and ('_surface_' in key or '_migration_' in key)
    }
    out = {}
    for key in sorted(base | dynamic):
        if key not in row or row[key] == '':
            continue
        try:
            out[key] = float(row[key])
        except ValueError:
            out[key] = row[key]
    return out


def runtime_log_evidence(log_path):
    if not log_path.is_file():
        return {'status': 'MISSING'}
    text = log_path.read_text(errors='replace')
    time_steps = []
    for match in re.finditer(
        r'Time Step\s+(\d+),\s*time\s*=\s*([0-9.eE+\-]+)(?:,\s*dt\s*=\s*([0-9.eE+\-]+))?',
        text,
    ):
        time_steps.append({
            'step': int(match.group(1)),
            'time_s': float(match.group(2)),
            'dt_s': float(match.group(3)) if match.group(3) else None,
        })
    nonlinear_iterations = [
        int(value)
        for value in re.findall(
            r'Nonlinear solve converged due to\s+\S+\s+iterations\s+(\d+)', text
        )
    ]
    negative_density = None
    negative_match = re.search(
        r'requires electron_number_density\s*>=\s*0.*?Got\s+(-?[0-9.eE+\-]+)',
        text,
        flags=re.DOTALL,
    )
    if negative_match:
        negative_density = float(negative_match.group(1))
    return {
        'status': 'MEASURED',
        'time_steps': time_steps,
        'last_attempted_step': time_steps[-1]['step'] if time_steps else None,
        'last_attempted_time_s': time_steps[-1]['time_s'] if time_steps else None,
        'converged_nonlinear_iterations': nonlinear_iterations,
        'negative_electron_density_iterate_m3': negative_density,
    }


def row_at_time(rows, target, *, atol=1.0e-18):
    for row in rows:
        raw = row.get('time')
        if raw in (None, ''):
            continue
        try:
            time_value = float(raw)
        except ValueError:
            continue
        if math.isclose(time_value, target, rel_tol=0.0, abs_tol=atol):
            return select_row(row)
    return None


a6_text, a6_meta = a6._build_a6_case_input(
    base_text,
    parameters=a7._a6_parameters(params),
    mode='comsol_wall',
)
a7_e_text, a7_e_meta = a7._build_a7_case_input(
    base_text, parameters=params, mode='electron_thermal_only'
)
a7_c_text, a7_c_meta = a7._build_a7_case_input(
    base_text, parameters=params, mode='combined_thermal'
)

case_specs = [
    {
        'name': 'a6_matched_ledger__dt_1p000em10',
        'family': 'a6_matched_ledger',
        'dt_s': BASELINE_DT,
        'text': a6_text,
        'meta': a6_meta,
    },
]
for dt in ALL_DTS:
    suffix = dt_label(dt)
    case_specs.extend((
        {
            'name': f'a7_electron_thermal_only__dt_{suffix}',
            'family': 'a7_electron_thermal_only',
            'dt_s': dt,
            'text': a7_e_text,
            'meta': a7_e_meta,
        },
        {
            'name': f'a7_combined_thermal__dt_{suffix}',
            'family': 'a7_combined_thermal',
            'dt_s': dt,
            'text': a7_c_text,
            'meta': a7_c_meta,
        },
    ))

construction = {}
for cfg in case_specs:
    construction[cfg['name']] = stage(
        cfg['name'], cfg['text'], cfg['meta'], dt=cfg['dt_s']
    )

summary = {
    'controller': 194,
    'hypothesis_owner': 200,
    'repository_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'executable_realpath': str(EXE.resolve()),
    'executable_sha256': sha256(EXE),
    'baseline_dt_s': BASELINE_DT,
    'refinement_dt_s': list(REFINEMENT_DTS),
    'equal_physical_end_time_s': TARGET_END,
    'physics_semantics_changed': False,
    'diagnostic_infrastructure_version': 'A7-DIAG-8-H6-EQUAL-TIME',
    'construction': construction,
    'cases': {},
    'equal_time_samples': {},
    'reproduction_disposition': 'PENDING_EXECUTION',
    'status': 'RUNNING',
}

capture_complete = True
for cfg in case_specs:
    name = cfg['name']
    dt = cfg['dt_s']
    case_dir = CASES / name
    p2_log = LOGS / f'{name}_p2.log'
    runtime_log = LOGS / f'{name}_runtime.log'
    p2 = q0_run._p2(EXE, case_dir, p2_log, 300.0)
    item = {
        'family': cfg['family'],
        'dt_s': dt,
        'expected_steps': int(round(TARGET_END / dt)),
        'p2': p2,
        'runtime': None,
        'runtime_log_evidence': None,
        'rows': [],
        'input_sha256': sha256(case_dir / 'input.i'),
    }
    if p2['returncode'] != 0:
        item['classification'] = 'NOT_EVALUATED_P2_FAILURE'
        capture_complete = False
        summary['cases'][name] = item
        continue

    runtime = q0_run._runtime(EXE, case_dir, runtime_log, 1200.0)
    item['runtime'] = runtime
    item['runtime_log_evidence'] = runtime_log_evidence(runtime_log)
    csv_path = case_dir / 'input_out.csv'
    rows = read_rows(csv_path)
    if csv_path.is_file():
        item['csv_sha256'] = sha256(csv_path)
    item['row_count'] = len(rows)
    item['columns'] = list(rows[0].keys()) if rows else []
    item['rows'] = [select_row(row) for row in rows]
    item['last_completed_time_s'] = (
        float(rows[-1]['time']) if rows and rows[-1].get('time') not in (None, '') else None
    )

    if not rows:
        item['classification'] = 'NOT_EVALUATED_NO_TIMELINE'
        capture_complete = False
    elif runtime['returncode'] == 0 and math.isclose(
        item['last_completed_time_s'], TARGET_END, rel_tol=0.0, abs_tol=1.0e-18
    ):
        item['classification'] = 'MEASURED_COMPLETE'
    elif runtime['returncode'] != 0:
        item['classification'] = 'MEASURED_RUNTIME_FAILURE'
    else:
        item['classification'] = 'INCOMPLETE_TIMELINE'
        capture_complete = False
    summary['cases'][name] = item

comparison_times = (1.0e-10, 2.0e-10, 3.0e-10, 4.0e-10, 5.0e-10)
for family in ('a7_electron_thermal_only', 'a7_combined_thermal'):
    family_samples = {}
    for dt in ALL_DTS:
        suffix = dt_label(dt)
        name = f'{family}__dt_{suffix}'
        case_dir = CASES / name
        rows = read_rows(case_dir / 'input_out.csv')
        dt_samples = {}
        for target in comparison_times:
            sample = row_at_time(rows, target)
            if sample is not None:
                dt_samples[f'{target:.17g}'] = sample
        family_samples[f'{dt:.17g}'] = {
            'case': name,
            'runtime_returncode': summary['cases'][name]['runtime']['returncode'] if summary['cases'][name]['runtime'] else None,
            'classification': summary['cases'][name]['classification'],
            'last_completed_time_s': summary['cases'][name].get('last_completed_time_s'),
            'samples': dt_samples,
        }
    summary['equal_time_samples'][family] = family_samples

fingerprint = hashlib.sha256()
for name in sorted(summary['cases']):
    item = summary['cases'][name]
    fingerprint.update(name.encode())
    fingerprint.update(item.get('input_sha256', '').encode())
    fingerprint.update(item.get('csv_sha256', '').encode())
summary['common_evidence_identity'] = (
    f"issue194-h6-equal-time-{summary['repository_head'][:12]}-{fingerprint.hexdigest()[:16]}"
)
summary['status'] = (
    'H6_EQUAL_TIME_EVIDENCE_CAPTURED'
    if capture_complete
    else 'H6_EQUAL_TIME_EVIDENCE_PARTIAL'
)
summary['reproduction_disposition'] = (
    'READY_FOR_H6_EQUAL_TIME_ANALYSIS'
    if capture_complete
    else 'H6_REFINEMENT_SURFACE_INCOMPLETE'
)
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
print(json.dumps({
    'status': summary['status'],
    'common_evidence_identity': summary['common_evidence_identity'],
    'cases': {
        name: {
            'classification': item['classification'],
            'runtime_returncode': item['runtime']['returncode'] if item['runtime'] else None,
            'last_completed_time_s': item.get('last_completed_time_s'),
        }
        for name, item in summary['cases'].items()
    },
}, indent=2, sort_keys=True))
