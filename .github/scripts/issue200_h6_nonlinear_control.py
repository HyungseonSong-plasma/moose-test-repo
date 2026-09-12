import argparse
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
OUT = ROOT / 'issue200-h6-results'
CASES = OUT / 'cases'
LOGS = OUT / 'logs'
SOURCE = ROOT / 'experiments/Issue91_real_qvt_r3/r3_e0'
EXE = ROOT / 'physics_app/physics-opt'
DT = 1.0e-10
END = 5.0e-10
EQUIV_TIMES = (1.0e-10, 2.0e-10)
EQUIV_REL_TOL = 1.0e-4
CONTROLS = (
    {'id': 'baseline_fullstep', 'line_search': 'none', 'damping': None},
    {'id': 'basic_damp_0p5', 'line_search': 'basic', 'damping': 0.5},
    {'id': 'basic_damp_0p25', 'line_search': 'basic', 'damping': 0.25},
    {'id': 'backtracking', 'line_search': 'bt', 'damping': None},
)

spec = json.loads(
    (ROOT / 'experiments/Issue27_surface_reactions/A7_comsol_electron_wall/experiment.json').read_text()
)
params = spec['parameters']
base_text = (SOURCE / 'heavy_base.i').read_text()


def add_pp(text, name, body):
    if mb.has_block(text, f'Postprocessors/{name}'):
        return text
    return mb.insert_child_block(text, 'Postprocessors', f'  [{name}]\n{body}\n  []')


def solver_options(control):
    iname = '-pc_type -pc_factor_shift_type'
    values = 'lu NONZERO'
    if control['damping'] is not None:
        iname += ' -snes_linesearch_damping'
        values += f" {control['damping']:.17g}"
    return iname, values


def instrument(text, control):
    text = mp.upsert_parameter(text, 'Executioner', 'dt', f'{DT:.17g}')
    text = mp.upsert_parameter(text, 'Executioner', 'end_time', f'{END:.17g}')
    text = mp.upsert_parameter(text, 'Executioner', 'line_search', control['line_search'])
    iname, values = solver_options(control)
    text = mp.upsert_parameter(
        text, 'Executioner', 'petsc_options', "'-snes_monitor -snes_converged_reason'"
    )
    text = mp.upsert_parameter(text, 'Executioner', 'petsc_options_iname', f"'{iname}'")
    text = mp.upsert_parameter(text, 'Executioner', 'petsc_options_value', f"'{values}'")
    for pp in (
        'n_e_inventory', 'n_e_min', 'n_e_max', 'n_e_avg',
        'mass_O2p', 'mass_Om', 'mass_Op',
        'r31_charge_integral', 'r31_gauss_flux_charge',
    ):
        if mb.has_block(text, f'Postprocessors/{pp}'):
            text = mp.upsert_parameter(
                text, f'Postprocessors/{pp}', 'execute_on', "'INITIAL TIMESTEP_END'"
            )
    text = add_pp(
        text, 'issue200_rho_q_min',
        "    type = ADElementExtremeFunctorValue\n"
        "    functor = charge_density\n"
        "    value_type = min\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = add_pp(
        text, 'issue200_rho_q_max',
        "    type = ADElementExtremeFunctorValue\n"
        "    functor = charge_density\n"
        "    value_type = max\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = add_pp(
        text, 'issue200_phi_min',
        "    type = ElementExtremeValue\n"
        "    variable = potential_plasma\n"
        "    value_type = min\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = add_pp(
        text, 'issue200_phi_max',
        "    type = ElementExtremeValue\n"
        "    variable = potential_plasma\n"
        "    value_type = max\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = add_pp(
        text, 'issue200_phi_avg',
        "    type = ElementAverageValue\n"
        "    variable = potential_plasma\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    return text


def normalize_controls(text):
    allowed = {'line_search', 'petsc_options', 'petsc_options_iname', 'petsc_options_value'}
    out = []
    in_executioner = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == '[Executioner]':
            in_executioner = True
        elif in_executioner and stripped == '[]':
            in_executioner = False
        match = re.match(r'\s*([A-Za-z0-9_]+)\s*=.*$', line)
        if in_executioner and match and match.group(1) in allowed:
            out.append(f'  {match.group(1)} = <NUMERICAL_CONTROL>')
        else:
            out.append(line)
    return '\n'.join(out)


def p0_self_test():
    rendered = {}
    for control in CONTROLS:
        rendered[control['id']], _ = _promote_current_acceptance_types(
            instrument(base_text, control)
        )
    baseline = normalize_controls(rendered['baseline_fullstep'])
    for control in CONTROLS[1:]:
        if normalize_controls(rendered[control['id']]) != baseline:
            raise AssertionError(f"{control['id']}: non-numerical semantic drift")
    negative = rendered['baseline_fullstep'].replace('T_g_value = 600', 'T_g_value = 601', 1)
    if normalize_controls(negative) == baseline:
        raise AssertionError('physics negative mutation was not detected')
    expected = {
        'baseline_fullstep': ('line_search = none', False),
        'basic_damp_0p5': ('line_search = basic', True),
        'basic_damp_0p25': ('line_search = basic', True),
        'backtracking': ('line_search = bt', False),
    }
    for control_id, (line_token, needs_damping) in expected.items():
        candidate = rendered[control_id]
        if line_token not in candidate:
            raise AssertionError(f'{control_id}: line-search contract missing')
        if ('-snes_linesearch_damping' in candidate) != needs_damping:
            raise AssertionError(f'{control_id}: damping contract mismatch')
    return {
        'status': 'PASS',
        'positive_control': 'solver variants differ only on declared numerical controls',
        'negative_mutation': 'T_g_value 600 -> 601 is rejected as physics drift',
    }


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def stage(name, text, meta, control):
    target = CASES / name
    current, promotion = _promote_current_acceptance_types(instrument(text, control))
    staged = stage_case(
        SOURCE,
        target,
        input_text=current,
        purge_directory_names=('.jitcache', 'checkpoint', 'checkpoints'),
        purge_patterns=('input_out*', '*.log', '*.e', '*.exo', 'prepare_evidence.json'),
    )
    evidence = {
        'source_meta': meta,
        'current_physics_object_promotion': promotion,
        'dt_s': DT,
        'end_time_s': END,
        'solver_control': control,
        'physics_semantics_changed': False,
    }
    (target / 'prepare_evidence.json').write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + '\n'
    )
    return {'staging': staged, 'meta': evidence}


def read_rows(path):
    if not path.is_file():
        return []
    with path.open(newline='') as handle:
        return list(csv.DictReader(handle))


def selected(row):
    out = {}
    keys = (
        'time', 'n_e_inventory', 'n_e_min', 'n_e_max', 'n_e_avg',
        'r31_charge_integral', 'r31_gauss_flux_charge',
        'issue200_rho_q_min', 'issue200_rho_q_max',
        'issue200_phi_min', 'issue200_phi_max', 'issue200_phi_avg',
        a7.THERMAL_PP,
    )
    for key in keys:
        if row.get(key, '') == '':
            continue
        try:
            out[key] = float(row[key])
        except ValueError:
            out[key] = row[key]
    return out


def log_evidence(path):
    text = path.read_text(errors='replace') if path.is_file() else ''
    steps = [
        {'step': int(s), 'time_s': float(t), 'dt_s': float(dt) if dt else None}
        for s, t, dt in re.findall(
            r'Time Step\s+(\d+),\s*time\s*=\s*([0-9.eE+\-]+)(?:,\s*dt\s*=\s*([0-9.eE+\-]+))?',
            text,
        )
    ]
    match = re.search(
        r'requires electron_number_density\s*>=\s*0.*?Got\s+(-?[0-9.eE+\-]+)',
        text,
        flags=re.DOTALL,
    )
    return {
        'last_attempted_step': steps[-1]['step'] if steps else None,
        'last_attempted_time_s': steps[-1]['time_s'] if steps else None,
        'negative_electron_density_iterate_m3': float(match.group(1)) if match else None,
        'converged_nonlinear_iterations': [
            int(v) for v in re.findall(
                r'Nonlinear solve converged due to\s+\S+\s+iterations\s+(\d+)', text
            )
        ],
    }


def row_at(rows, target):
    for row in rows:
        if row.get('time', '') != '' and math.isclose(
            float(row['time']), target, rel_tol=0.0, abs_tol=1.0e-18
        ):
            return selected(row)
    return None


def rel_diff(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1.0e-30)


def equivalence(family, control_id):
    base = read_rows(CASES / f'{family}__baseline_fullstep' / 'input_out.csv')
    test = read_rows(CASES / f'{family}__{control_id}' / 'input_out.csv')
    comparisons = []
    max_rel = 0.0
    complete = True
    for target in EQUIV_TIMES:
        b = row_at(base, target)
        c = row_at(test, target)
        if b is None or c is None:
            complete = False
            comparisons.append({'time_s': target, 'status': 'MISSING_OVERLAP_ROW'})
            continue
        metrics = {}
        for metric in ('n_e_inventory', 'r31_charge_integral', 'issue200_phi_max'):
            if metric not in b or metric not in c:
                complete = False
                metrics[metric] = {'status': 'MISSING'}
                continue
            value = rel_diff(float(b[metric]), float(c[metric]))
            max_rel = max(max_rel, value)
            metrics[metric] = {'relative_difference': value}
        comparisons.append({'time_s': target, 'metrics': metrics})
    return {
        'complete': complete,
        'max_relative_difference': max_rel,
        'relative_tolerance': EQUIV_REL_TOL,
        'passed': complete and max_rel <= EQUIV_REL_TOL,
        'comparisons': comparisons,
    }


parser = argparse.ArgumentParser()
parser.add_argument('--self-test', action='store_true')
args = parser.parse_args()
if args.self_test:
    print(json.dumps(p0_self_test(), indent=2, sort_keys=True))
    raise SystemExit(0)

CASES.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)
p0 = p0_self_test()

a6_text, a6_meta = a6._build_a6_case_input(
    base_text, parameters=a7._a6_parameters(params), mode='comsol_wall'
)
a7_e_text, a7_e_meta = a7._build_a7_case_input(
    base_text, parameters=params, mode='electron_thermal_only'
)
a7_c_text, a7_c_meta = a7._build_a7_case_input(
    base_text, parameters=params, mode='combined_thermal'
)

case_specs = [
    ('a6_matched_ledger__baseline_fullstep', 'a6_matched_ledger', a6_text, a6_meta, CONTROLS[0])
]
for family, text, meta in (
    ('a7_electron_thermal_only', a7_e_text, a7_e_meta),
    ('a7_combined_thermal', a7_c_text, a7_c_meta),
):
    for control in CONTROLS:
        case_specs.append((f"{family}__{control['id']}", family, text, meta, control))

summary = {
    'controller': 194,
    'hypothesis_owner': 200,
    'repository_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'executable_realpath': str(EXE.resolve()),
    'executable_sha256': sha256(EXE),
    'dt_s': DT,
    'end_time_s': END,
    'physics_semantics_changed': False,
    'diagnostic_infrastructure_version': 'A7-DIAG-10-H6-NONLINEAR-CONTROL',
    'p0_self_test': p0,
    'controls': list(CONTROLS),
    'construction': {},
    'cases': {},
    'physics_equivalence': {},
}
for name, family, text, meta, control in case_specs:
    summary['construction'][name] = stage(name, text, meta, control)

capture_complete = True
for name, family, _, _, control in case_specs:
    case_dir = CASES / name
    p2_log = LOGS / f'{name}_p2.log'
    runtime_log = LOGS / f'{name}_runtime.log'
    p2 = q0_run._p2(EXE, case_dir, p2_log, 300.0)
    item = {
        'family': family,
        'control': control,
        'p2': p2,
        'runtime': None,
        'input_sha256': sha256(case_dir / 'input.i'),
    }
    if p2['returncode'] != 0:
        item['classification'] = 'NOT_EVALUATED_P2_FAILURE'
        capture_complete = False
        summary['cases'][name] = item
        continue
    runtime = q0_run._runtime(EXE, case_dir, runtime_log, 1200.0)
    rows = read_rows(case_dir / 'input_out.csv')
    item['runtime'] = runtime
    item['runtime_log_evidence'] = log_evidence(runtime_log)
    item['row_count'] = len(rows)
    item['rows'] = [selected(row) for row in rows]
    if rows:
        item['csv_sha256'] = sha256(case_dir / 'input_out.csv')
        item['last_completed_time_s'] = float(rows[-1]['time'])
        item['final_n_e_min_m3'] = float(rows[-1]['n_e_min'])
    else:
        item['last_completed_time_s'] = None
        item['final_n_e_min_m3'] = None
    if not rows:
        item['classification'] = 'NOT_EVALUATED_NO_TIMELINE'
        capture_complete = False
    elif (
        runtime['returncode'] == 0
        and math.isclose(item['last_completed_time_s'], END, rel_tol=0.0, abs_tol=1.0e-18)
        and item['final_n_e_min_m3'] >= 0.0
    ):
        item['classification'] = 'MEASURED_COMPLETE_PHYSICALLY_ADMISSIBLE'
    elif runtime['returncode'] != 0:
        item['classification'] = 'MEASURED_RUNTIME_FAILURE'
    else:
        item['classification'] = 'INCOMPLETE_TIMELINE'
        capture_complete = False
    summary['cases'][name] = item

for family in ('a7_electron_thermal_only', 'a7_combined_thermal'):
    summary['physics_equivalence'][family] = {
        control['id']: equivalence(family, control['id']) for control in CONTROLS[1:]
    }

known_good = (
    summary['cases']['a6_matched_ledger__baseline_fullstep']['classification']
    == 'MEASURED_COMPLETE_PHYSICALLY_ADMISSIBLE'
)
combined_passes = []
electron_passes = []
for control in CONTROLS[1:]:
    cid = control['id']
    for family, bucket in (
        ('a7_combined_thermal', combined_passes),
        ('a7_electron_thermal_only', electron_passes),
    ):
        case = summary['cases'][f'{family}__{cid}']
        equiv = summary['physics_equivalence'][family][cid]
        if case['classification'] == 'MEASURED_COMPLETE_PHYSICALLY_ADMISSIBLE' and equiv['passed']:
            bucket.append(cid)

if not known_good:
    disposition = 'NOT_EVALUATED_KNOWN_GOOD_CONTROL_FAILED'
elif combined_passes:
    disposition = 'H6_SUPPORTED_DOWNSTREAM_NUMERICAL_SOLVER_LIMITATION'
elif electron_passes:
    disposition = 'H6_PARTIALLY_SUPPORTED_ELECTRON_ONLY_CONTROL_RECOVERY'
else:
    baseline_time = summary['cases']['a7_combined_thermal__baseline_fullstep']['last_completed_time_s'] or 0.0
    strongest_time = max(
        summary['cases'][f"a7_combined_thermal__{control['id']}"]['last_completed_time_s'] or 0.0
        for control in CONTROLS[1:]
    )
    disposition = (
        'H6_NONLINEAR_CONTROL_EXTENDS_BUT_DOES_NOT_CLOSE_HORIZON'
        if strongest_time > baseline_time + 0.5 * DT
        else 'H6_NOT_RESOLVED_BY_BOUNDED_GLOBALIZATION_CONTROLS'
    )

fingerprint = hashlib.sha256()
for name in sorted(summary['cases']):
    item = summary['cases'][name]
    fingerprint.update(name.encode())
    fingerprint.update(item.get('input_sha256', '').encode())
    fingerprint.update(item.get('csv_sha256', '').encode())
summary['evidence_identity'] = (
    f"issue200-h6-nonlinear-{summary['repository_head'][:12]}-{fingerprint.hexdigest()[:16]}"
)
summary['h6_disposition'] = disposition
summary['status'] = (
    'H6_NONLINEAR_CONTROL_EVIDENCE_CAPTURED'
    if capture_complete
    else 'H6_NONLINEAR_CONTROL_EVIDENCE_PARTIAL'
)
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
print(json.dumps({
    'status': summary['status'],
    'h6_disposition': disposition,
    'evidence_identity': summary['evidence_identity'],
    'combined_physics_equivalent_complete_controls': combined_passes,
    'electron_physics_equivalent_complete_controls': electron_passes,
    'cases': {
        name: {
            'classification': item['classification'],
            'runtime_returncode': item['runtime']['returncode'] if item.get('runtime') else None,
            'last_completed_time_s': item.get('last_completed_time_s'),
            'negative_electron_density_iterate_m3': (
                item.get('runtime_log_evidence') or {}
            ).get('negative_electron_density_iterate_m3'),
        }
        for name, item in summary['cases'].items()
    },
}, indent=2, sort_keys=True))
