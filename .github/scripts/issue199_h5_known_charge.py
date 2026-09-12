import csv
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue193_a8_see_acceptance.run import _promote_current_acceptance_types
from physics_harness.execution.cases import stage_case

ROOT = Path('/workspace')
OUT = ROOT / 'issue199-h5-results'
CASES = OUT / 'cases'
LOGS = OUT / 'logs'
SOURCE = ROOT / 'experiments/Issue1_reactor_o2plus_integration/poisson_analytic'
EXE = ROOT / 'physics_app/physics-opt'
CASES.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

E_CHARGE = 1.602176634e-19
AVOGADRO = 6.02214076e23
EPS0 = 8.8541878128e-12
RHO0 = 1.0e-9
W_TARGET = 1.0e-6
M_I = 0.032003320316217242
TARGET_N = RHO0 * W_TARGET * AVOGADRO / M_I
REL_TOL = 2.0e-2
ZERO_PHI_ABS_TOL_V = 1.0e-8

BASE_TEXT = (SOURCE / 'poisson_analytic.i').read_text()


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def replace_scalar(text, name, value):
    pattern = rf'(?m)^{re.escape(name)}\s*=\s*.*$'
    replacement = f'{name} = {value:.17g}'
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f'failed to replace scalar {name!r}')
    return updated


def rel_err(actual, expected):
    return abs(actual - expected) / max(abs(actual), abs(expected), 1.0e-300)


def read_last_row(path):
    with path.open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError(f'no CSV rows in {path}')
    return rows[-1]


def build_case_text(*, w_target, electron_density):
    text = BASE_TEXT
    text = replace_scalar(text, 'rho0', RHO0)
    text = replace_scalar(text, 'w_target_value', w_target)
    text = replace_scalar(text, 'electron_density_value', electron_density)
    promoted, promotion = _promote_current_acceptance_types(text)
    return promoted, promotion


def run_case(name, *, w_target, electron_density):
    text, promotion = build_case_text(
        w_target=w_target,
        electron_density=electron_density,
    )
    case_dir = CASES / name
    staged = stage_case(
        SOURCE,
        case_dir,
        input_text=text,
        purge_directory_names=('.jitcache', 'checkpoint', 'checkpoints'),
        purge_patterns=('input_out*', '*.log', '*.e', '*.exo'),
    )
    p2 = q0_run._p2(EXE, case_dir, LOGS / f'{name}_p2.log', 300.0)
    item = {
        'staging': staged,
        'current_physics_object_promotion': promotion,
        'input_sha256': sha256(case_dir / 'input.i'),
        'p2': p2,
        'runtime': None,
        'measured': None,
    }
    if p2['returncode'] != 0:
        item['classification'] = 'NOT_EVALUATED_P2_FAILURE'
        return item
    runtime = q0_run._runtime(EXE, case_dir, LOGS / f'{name}_runtime.log', 300.0)
    item['runtime'] = runtime
    csv_path = case_dir / 'input_out.csv'
    if runtime['returncode'] != 0 or not csv_path.is_file():
        item['classification'] = 'NOT_EVALUATED_RUNTIME_FAILURE'
        return item
    row = read_last_row(csv_path)
    item['csv_sha256'] = sha256(csv_path)
    item['measured'] = {
        'w_avg': float(row['w_avg']),
        'phi_avg_V': float(row['phi_avg']),
        'phi_max_V': float(row['phi_max']),
        'phi_min_V': float(row['phi_min']),
    }
    item['classification'] = 'MEASURED'
    return item


cases = {
    'zero_charge': {
        'w_target': 0.0,
        'electron_density': 0.0,
        'expected_charge_density_C_m3': 0.0,
    },
    'positive_known_charge': {
        'w_target': W_TARGET,
        'electron_density': 0.0,
        'expected_charge_density_C_m3': E_CHARGE * TARGET_N,
    },
    'negative_known_charge': {
        'w_target': 0.0,
        'electron_density': TARGET_N,
        'expected_charge_density_C_m3': -E_CHARGE * TARGET_N,
    },
}

summary = {
    'controller': 194,
    'hypothesis_owner': 199,
    'repository_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'executable_realpath': str(EXE.resolve()),
    'executable_sha256': sha256(EXE),
    'diagnostic': 'independent known-charge electrostatic scale/sign/reference test',
    'physics_semantics_changed': False,
    'constants': {
        'elementary_charge_C': E_CHARGE,
        'avogadro_mol_inv': AVOGADRO,
        'eps0_F_m': EPS0,
        'rho0_kg_m3': RHO0,
        'ion_molar_mass_kg_mol': M_I,
        'positive_mass_fraction': W_TARGET,
        'known_number_density_m3': TARGET_N,
        'relative_tolerance': REL_TOL,
        'zero_phi_absolute_tolerance_V': ZERO_PHI_ABS_TOL_V,
    },
    'cases': {},
    'checks': {},
    'status': 'RUNNING',
}

scientific_ready = True
for name, cfg in cases.items():
    item = run_case(
        name,
        w_target=cfg['w_target'],
        electron_density=cfg['electron_density'],
    )
    charge_density = cfg['expected_charge_density_C_m3']
    source = charge_density / EPS0
    item['expected'] = {
        'charge_density_C_m3': charge_density,
        'poisson_source_V_m2': source,
        'phi_center_V': source / 8.0,
        'phi_average_V': source / 12.0,
    }
    if item['classification'] != 'MEASURED':
        scientific_ready = False
    summary['cases'][name] = item

if scientific_ready:
    zero = summary['cases']['zero_charge']['measured']
    pos = summary['cases']['positive_known_charge']
    neg = summary['cases']['negative_known_charge']

    pos_phi_expected = pos['expected']['phi_center_V']
    pos_avg_expected = pos['expected']['phi_average_V']
    neg_phi_expected = neg['expected']['phi_center_V']
    neg_avg_expected = neg['expected']['phi_average_V']

    checks = {
        'zero_reference_phi': max(abs(zero['phi_min_V']), abs(zero['phi_max_V']), abs(zero['phi_avg_V'])) <= ZERO_PHI_ABS_TOL_V,
        'positive_phi_scale': rel_err(pos['measured']['phi_max_V'], pos_phi_expected) <= REL_TOL,
        'positive_phi_average': rel_err(pos['measured']['phi_avg_V'], pos_avg_expected) <= REL_TOL,
        'negative_phi_scale': rel_err(neg['measured']['phi_min_V'], neg_phi_expected) <= REL_TOL,
        'negative_phi_average': rel_err(neg['measured']['phi_avg_V'], neg_avg_expected) <= REL_TOL,
        'positive_mass_fraction': rel_err(pos['measured']['w_avg'], W_TARGET) <= 1.0e-8,
        'negative_zero_ion_fraction': abs(neg['measured']['w_avg']) <= 1.0e-12,
        'charge_sign_response': pos['measured']['phi_max_V'] > 0.0 and neg['measured']['phi_min_V'] < 0.0,
        'positive_negative_gain_symmetry': rel_err(abs(pos['measured']['phi_max_V']), abs(neg['measured']['phi_min_V'])) <= REL_TOL,
    }
    summary['checks'] = checks
    summary['errors'] = {
        'positive_phi_center_relative': rel_err(pos['measured']['phi_max_V'], pos_phi_expected),
        'positive_phi_average_relative': rel_err(pos['measured']['phi_avg_V'], pos_avg_expected),
        'negative_phi_center_relative': rel_err(neg['measured']['phi_min_V'], neg_phi_expected),
        'negative_phi_average_relative': rel_err(neg['measured']['phi_avg_V'], neg_avg_expected),
        'positive_negative_gain_relative': rel_err(abs(pos['measured']['phi_max_V']), abs(neg['measured']['phi_min_V'])),
    }
    passed = all(checks.values())
    summary['status'] = 'H5_KNOWN_CHARGE_PASS' if passed else 'H5_KNOWN_CHARGE_FAIL'
else:
    summary['status'] = 'H5_KNOWN_CHARGE_NOT_EVALUATED'

fingerprint = hashlib.sha256()
fingerprint.update(summary['repository_head'].encode())
fingerprint.update(summary['executable_sha256'].encode())
for name in sorted(summary['cases']):
    item = summary['cases'][name]
    fingerprint.update(name.encode())
    fingerprint.update(item.get('input_sha256', '').encode())
    fingerprint.update(item.get('csv_sha256', '').encode())
summary['evidence_identity'] = (
    f"issue199-h5-known-charge-{summary['repository_head'][:12]}-{fingerprint.hexdigest()[:16]}"
)

(OUT / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
print(json.dumps(summary, indent=2, sort_keys=True))

if summary['status'] == 'H5_KNOWN_CHARGE_PASS':
    raise SystemExit(0)
if summary['status'] == 'H5_KNOWN_CHARGE_NOT_EVALUATED':
    raise SystemExit(2)
raise SystemExit(1)
