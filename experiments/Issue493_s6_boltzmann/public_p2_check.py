#!/usr/bin/env python3
"""P2 ONLY: native --check-input for public Boltzmann S6-417/941 B/C.

Uses publicly committed candidate decks and independently calculated tables.
No old protected rate file, MCS source, private GitHub secret, P3 solve, or
P4 physical validation is accessed or started. Science stays HOLD.
"""
from __future__ import annotations
import argparse
import base64
import io
import tarfile
import hashlib
import json
import math
import os
import pathlib
import shlex
import shutil
import subprocess
import sys

BASE = pathlib.Path(__file__).resolve().parent
DECKS = pathlib.Path('experiments/Issue493_s6_boltzmann/public_p2_decks')
CHEM = pathlib.Path('experiments/Issue395_powered_chemistry_ladder')
RATES = pathlib.Path('physics_app/data/electron_impact/boltz')
VARIANTS = ('B', 'C')
CASES = ('417', '941')
PACK_SHA = '9e801cc6dca3860750b7b97fb6ceca8e6060a3c894dd616cbaf688f529fea240'
PINNED_SOURCE = '29d1acc6ef7969908b86719e4b95c73a1565136d'
PINNED_CANDIDATE = 'bebaf47a33ff5ee1d6b933d9691bf48f5ec0f947'
# This module is executed by file path; add the owning repository root for harness imports.
sys.path.insert(0, str(BASE.parents[1]))
from physics_harness.execution.native_gates import (
    P1GateError, require_p1_success, run_p2_checked,
)
from physics_harness.adapters.moose.check_input import classify_failure

PINNED_OCI = ('ghcr.io/hyungseonsong-plasma/physics-build-base@'
              'sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008')


def sha(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def assert_directory(p: pathlib.Path, purpose: str):
    if not p.is_dir():
        raise ValueError(f'missing {purpose}: {p}')


def ensure_public_decks(control: pathlib.Path):
    directory = control / DECKS
    archive = control / 'experiments/Issue493_s6_boltzmann/public_p2_decks.tar.xz.b64'
    raw = base64.b64decode(archive.read_text().encode('ascii'), validate=False)
    if hashlib.sha256(raw).hexdigest() != PACK_SHA:
        raise ValueError('public input deck archive hash changed')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:xz') as tar:
        members = tar.getmembers()
        if len(members) != 45 or any(
            not item.isfile() or item.issym() or item.islnk() or
            item.name.startswith('/') or '..' in pathlib.PurePosixPath(item.name).parts or
            item.size > 70000 or not item.name.startswith(('S6-417-407-2069-H25/', 'S6-941-407-2069-H25/')) and
            item.name != 'manifest.json' for item in members):
            raise ValueError('unsafe or unexpected public input deck tar content')
        # The data-only archive is derived from publicly approved research
        # input templates, not original private rates or historical MCS output.
        if not directory.exists():
            directory.mkdir(parents=True)
            tar.extractall(directory, filter='data')
    if not (directory / 'manifest.json').is_file():
        raise ValueError('missing extracted public input deck manifest')


def preflight(control: pathlib.Path) -> dict:
    assert_directory(control, 'control checkout')
    ensure_public_decks(control)
    m = json.loads((control / 'experiments/Issue493_s6_boltzmann/public_p2_decks/manifest.json').read_text())
    if (m.get('schema') != 'issue493_public_native_p2_v1' or
        m.get('science') != 'SCIENCE_HOLD' or
        m.get('source_sha') != PINNED_SOURCE or
        m.get('candidate_sha') != PINNED_CANDIDATE or
        set(m.get('cases', {})) != set(CASES) or
        len(m.get('public_rate_sha256', {})) != 19):
        raise ValueError('public-data provenance or science invariant mismatched')
    data = control / RATES
    assert_directory(data, 'public Boltzmann rates')
    if {x.name for x in data.glob('EI-*.txt')} != set(m['public_rate_sha256']):
        raise ValueError('unexpected public Boltzmann table set')
    grid = None
    for name, expected in sorted(m['public_rate_sha256'].items()):
        path = data / name
        if sha(path) != expected:
            raise ValueError(f'public table content mismatch: {name}')
        rows = [tuple(map(float, line.split())) for line in path.read_text().splitlines()]
        if len(rows) != 100 or any(len(row) != 2 for row in rows):
            raise ValueError(f'wrong rate shape: {name}')
        if any(not math.isfinite(x) or not math.isfinite(y) or y < 0 for x, y in rows):
            raise ValueError(f'invalid rates: {name}')
        xs = [x for x, _ in rows]
        if any(x >= y for x, y in zip(xs, xs[1:])):
            raise ValueError(f'unsorted mean-energy grid: {name}')
        if grid is None:
            grid = xs
        if grid != xs:
            raise ValueError(f'non-common mean-energy grid: {name}')
    for case in CASES:
        record = m['cases'][case]
        folder = control / DECKS / record['name']
        active = set(record['active'])
        if len(active) != 5 or not active.issubset(m['public_rate_sha256']):
            raise ValueError(f'incorrect case-specific active rates: {case}')
        order = json.loads((folder / 'input_order.json').read_text())
        if order != record['input_order'] or len(order) != 10 or len(set(order)) != 10:
            raise ValueError(f'wrong ordered input deck: {case}')
        for variant in VARIANTS:
            names = set(order) | ({'migrated_continuity.i'} if variant == 'C' else set())
            actual = {p.name for p in (folder / variant).glob('*.i')}
            if actual != names or set(record['files_sha256'][variant]) != names:
                raise ValueError(f'wrong input files: {case}/{variant}')
            used_rates = set()
            for name in names:
                file = folder / variant / name
                if sha(file) != record['files_sha256'][variant][name]:
                    raise ValueError(f'input deck SHA mismatch: {case}/{variant}/{name}')
                text = file.read_text()
                import re
                used_rates.update(re.findall(r'rate_table_file\s*=\s*[\'\"]?private_rates/([\w.-]+\.txt)', text))
            if used_rates != active:
                raise ValueError(f'wrong active lookup bindings: {case}/{variant}: {sorted(used_rates)}')
        for name in order[1:]:
            if record['files_sha256']['B'][name] != record['files_sha256']['C'][name]:
                raise ValueError(f'unexpected overlay change: {case}/{name}')
    return {'P0': 'PASS', 'public_rate_count': 19, 'science': 'SCIENCE_HOLD',
            'cases': list(CASES), 'variants': list(VARIANTS), 'P2': 'NOT_RUN',
            'P3': 'NOT_RUN', 'P4': 'NOT_RUN'}


def check_head(repo: pathlib.Path, expected: str):
    value = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    if value != expected:
        raise ValueError(f'exact-source pin failed: {repo.name}')


def stage(control: pathlib.Path, historical: pathlib.Path, case: str, variant: str,
          folder: pathlib.Path, manifest: dict) -> list[str]:
    if folder.exists():
        raise ValueError('refuse overwriting any previously staged case')
    if (historical / CHEM / 'private_rates').exists():
        raise ValueError('prepared historical tree contains protected private rates')
    if not (historical / CHEM / 'baseline_plasma_plus_unstructured_cover_plus_wafer.msh').is_file():
        raise ValueError('required prepared public mesh is absent')
    shutil.copytree(historical, folder, symlinks=True,
        ignore=shutil.ignore_patterns('.git', 'private_rates', '*.e', '*.cpa.gz', '*.rd', 'plasma_cp'))
    rec = manifest['cases'][case]
    chemistry = folder / CHEM
    deck = control / DECKS / rec['name'] / variant
    for name in rec['input_order'] + (['migrated_continuity.i'] if variant == 'C' else []):
        shutil.copyfile(deck / name, chemistry / name)
    rate_dir = chemistry / 'private_rates'  # Historical MOOSE input-relative path only; values are PUBLIC.
    rate_dir.mkdir(mode=0o700)
    for name in rec['active']:
        shutil.copyfile(control / RATES / name, rate_dir / name)
    ordered = rec['input_order'] + (['migrated_continuity.i'] if variant == 'C' else [])
    return [str(CHEM / name) for name in ordered]


def check_native(candidate: pathlib.Path, staged: pathlib.Path, inputs: list[str],
                 logfile: pathlib.Path, timeout: int, p1_evidence: pathlib.Path) -> dict:
    # The shell is replaced with the one allowed P2 process, never a solve.
    command = ('exec /app/physics_app/physics-opt --check-input -i ' +
               ' '.join(shlex.quote(x) for x in inputs))
    args = ['docker', 'run', '--rm', '--entrypoint', '/bin/bash', '--user', '0:0',
            '--workdir', '/case', '--env', 'OXYGEN_RESEARCH_400=1',
            '--env', 'OXYGEN_RESEARCH_FULL24=0',
            '--env', 'OXYGEN_RESEARCH_EI2738_FORMULA=0',
            '--mount', f'type=bind,src={candidate.resolve()},dst=/app,readonly',
            '--mount', f'type=bind,src={staged.resolve()},dst=/case',
            PINNED_OCI, '-lc', 'set -euo pipefail; source /environment; ' + command]
    report = run_p2_checked(
        args, evidence=p1_evidence, source_root=candidate,
        binary=candidate / 'physics_app/physics-opt',
        source_sha=PINNED_CANDIDATE, image_ref=PINNED_OCI,
        cwd=staged, log_path=logfile, timeout_seconds=timeout,
        success_marker='Syntax OK', failure_classifier=classify_failure,
    )
    return {'P2': report['P2'], 'exit_code': report['returncode'],
            'timed_out': report['timed_out'], 'classification': report['classification'],
            'log_sha256': report['log_sha256'],
            'p1_binary_sha256': report['p1_binary_sha256'],
            'layers': len(inputs)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', required=True, type=pathlib.Path)
    parser.add_argument('--candidate', type=pathlib.Path)
    parser.add_argument('--historical', type=pathlib.Path)
    parser.add_argument('--output', type=pathlib.Path)
    parser.add_argument('--mode', choices=('preflight', 'native'), default='preflight')
    parser.add_argument('--p1-evidence', type=pathlib.Path)
    opts = parser.parse_args()
    control = opts.control.resolve()
    result = {'science': 'SCIENCE_HOLD', 'P2': 'NOT_RUN', 'P3': 'NOT_RUN', 'P4': 'NOT_RUN'}
    try:
        result.update(preflight(control))
        if opts.mode == 'native':
            if opts.candidate is None or opts.historical is None or opts.output is None or opts.p1_evidence is None:
                raise ValueError('native requires candidate, historical, output and P1 evidence')
            candidate, historical, output = (x.resolve() for x in (opts.candidate, opts.historical, opts.output))
            if output.exists():
                raise ValueError('output already exists; refusing overwrite')
            output.mkdir(parents=True, mode=0o700)
            check_head(candidate, PINNED_CANDIDATE)
            check_head(historical, PINNED_SOURCE)
            binary = candidate / 'physics_app/physics-opt'
            if not binary.is_file():
                raise ValueError('native candidate binary does not exist (P1 incomplete)')
            if shutil.which('docker') is None:
                raise ValueError('Docker unavailable on execution host')
            p1_identity = require_p1_success(
                opts.p1_evidence, source_root=candidate, binary=binary,
                source_sha=PINNED_CANDIDATE, image_ref=PINNED_OCI,
            )
            result['P1'] = 'PASS'
            result['p1_identity_sha256'] = sha(opts.p1_evidence)
            result['p1_binary_sha256'] = p1_identity['binary_sha256']
            result['candidate_binary_sha256'] = sha(binary)
            result['historical_mesh_sha256'] = sha(historical / CHEM / 'baseline_plasma_plus_unstructured_cover_plus_wafer.msh')
            manifest = json.loads((control / DECKS / 'manifest.json').read_text())
            result['checks'] = {}
            for case in CASES:
                result['checks'][case] = {}
                for variant in VARIANTS:
                    label = case + '_' + variant
                    dest = output / label
                    try:
                        inp = stage(control, historical, case, variant, dest, manifest)
                        result['checks'][case][variant] = check_native(candidate, dest, inp,
                                                       output / f'P2_{label}.log', 1200, opts.p1_evidence)
                    except Exception as exc:
                        result['checks'][case][variant] = {'P2': 'HOLD', 'error': str(exc)[:350]}
            vals = [v['P2'] for sub in result['checks'].values() for v in sub.values()]
            result['P2'] = 'PASS' if vals == ['PASS'] * 4 else 'HOLD'
    except Exception as exc:
        result['blocker'] = type(exc).__name__ + ': ' + str(exc)[:500]
        if opts.mode == 'native':
            result['P2'] = 'HOLD'
    finally:
        result['science'] = 'SCIENCE_HOLD'
        result['P3'] = 'NOT_RUN'
        result['P4'] = 'NOT_RUN'
        if opts.output is not None:
            opts.output.mkdir(parents=True, exist_ok=True)
            (opts.output / 'non_sensitive_p2_status.json').write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
        print(json.dumps(result, sort_keys=True))
    return 0 if result.get('P0') == 'PASS' and (opts.mode == 'preflight' or result.get('P2') == 'PASS') else 3


if __name__ == '__main__':
    sys.exit(main())
