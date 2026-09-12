import csv
import hashlib
import json
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
DT = 1.0e-10
STEPS = 5
END = DT * STEPS
spec = json.loads((ROOT / 'experiments/Issue27_surface_reactions/A7_comsol_electron_wall/experiment.json').read_text())
params = spec['parameters']
base_text = (SOURCE / 'heavy_base.i').read_text()


def add_pp(text, name, body):
    path = f'Postprocessors/{name}'
    if mb.has_block(text, path):
        return text
    return mb.insert_child_block(text, 'Postprocessors', f'  [{name}]\n{body}\n  []')


def instrument(text):
    text = mp.upsert_parameter(text, 'Executioner', 'dt', f'{DT:.17g}')
    text = mp.upsert_parameter(text, 'Executioner', 'end_time', f'{END:.17g}')
    for pp in ('n_e_inventory', 'n_e_min', 'n_e_max', 'n_e_avg', 'r31_charge_integral', 'r31_gauss_flux_charge'):
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


def stage(name, text, meta):
    target = CASES / name
    current_text, promotion = _promote_current_acceptance_types(instrument(text))
    staged = stage_case(
        SOURCE,
        target,
        input_text=current_text,
        purge_directory_names=('.jitcache', 'checkpoint', 'checkpoints'),
        purge_patterns=('input_out*', '*.log', '*.e', '*.exo', 'prepare_evidence.json'),
    )
    evidence = {'source_meta': meta, 'current_physics_object_promotion': promotion}
    (target / 'prepare_evidence.json').write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
    return {'staging': staged, 'meta': evidence}


a6_text, a6_meta = a6._build_a6_case_input(
    base_text,
    parameters=a7._a6_parameters(params),
    mode='comsol_wall',
)
a7_e_text, a7_e_meta = a7._build_a7_case_input(base_text, parameters=params, mode='electron_thermal_only')
a7_c_text, a7_c_meta = a7._build_a7_case_input(base_text, parameters=params, mode='combined_thermal')

construction = {
    'a6_matched_ledger': stage('a6_matched_ledger', a6_text, a6_meta),
    'a7_electron_thermal_only': stage('a7_electron_thermal_only', a7_e_text, a7_e_meta),
    'a7_combined_thermal': stage('a7_combined_thermal', a7_c_text, a7_c_meta),
}

summary = {
    'controller': 194,
    'repository_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'executable_realpath': str(EXE.resolve()),
    'executable_sha256': sha256(EXE),
    'dt_s': DT,
    'steps': STEPS,
    'end_time_s': END,
    'physics_semantics_changed': False,
    'diagnostic_infrastructure_version': 'A7-DIAG-7',
    'construction': construction,
    'cases': {},
    'reproduction_disposition': 'PENDING_EXECUTION',
    'status': 'RUNNING',
}

selected = [
    'time', 'domain_volume', 'n_e_inventory', 'n_e_min', 'n_e_max', 'n_e_avg',
    'r31_charge_integral', 'r31_gauss_flux_charge',
    'issue194_rho_q_min', 'issue194_rho_q_max',
    'issue194_phi_min', 'issue194_phi_max', 'issue194_phi_avg',
    a7.THERMAL_PP,
]

scientific_ready = True
for name in construction:
    case_dir = CASES / name
    p2 = q0_run._p2(EXE, case_dir, LOGS / f'{name}_p2.log', 300.0)
    item = {'p2': p2, 'runtime': None, 'rows': [], 'input_sha256': sha256(case_dir / 'input.i')}
    if p2['returncode'] != 0:
        item['classification'] = 'NOT_EVALUATED_P2_FAILURE'
        scientific_ready = False
        summary['cases'][name] = item
        continue
    runtime = q0_run._runtime(EXE, case_dir, LOGS / f'{name}_runtime.log', 900.0)
    item['runtime'] = runtime
    csv_path = case_dir / 'input_out.csv'
    if runtime['returncode'] != 0 or not csv_path.is_file():
        item['classification'] = 'NOT_EVALUATED_RUNTIME_FAILURE'
        scientific_ready = False
        summary['cases'][name] = item
        continue
    with csv_path.open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    item['csv_sha256'] = sha256(csv_path)
    item['row_count'] = len(rows)
    item['columns'] = list(rows[0].keys()) if rows else []
    for row in rows:
        out = {}
        for key in selected:
            if key in row and row[key] != '':
                try:
                    out[key] = float(row[key])
                except ValueError:
                    out[key] = row[key]
        item['rows'].append(out)
    item['classification'] = 'MEASURED' if len(rows) >= STEPS + 1 else 'INCOMPLETE_TIMELINE'
    if item['classification'] != 'MEASURED':
        scientific_ready = False
    summary['cases'][name] = item

fingerprint = hashlib.sha256()
for name in sorted(summary['cases']):
    item = summary['cases'][name]
    fingerprint.update(name.encode())
    fingerprint.update(item.get('input_sha256', '').encode())
    fingerprint.update(item.get('csv_sha256', '').encode())
summary['common_evidence_identity'] = f"issue194-a7-five-step-{summary['repository_head'][:12]}-{fingerprint.hexdigest()[:16]}"
summary['status'] = 'COMMON_EVIDENCE_MEASURED' if scientific_ready else 'NOT_EVALUATED_OR_INCOMPLETE'
summary['reproduction_disposition'] = 'READY_FOR_CAUSAL_ORDER_ANALYSIS' if scientific_ready else 'LOCAL_SURFACE_MISMATCH_UNRESOLVED'
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
print(json.dumps({'status': summary['status'], 'common_evidence_identity': summary['common_evidence_identity']}, indent=2))
