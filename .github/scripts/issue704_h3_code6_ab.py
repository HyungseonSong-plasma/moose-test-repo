#!/usr/bin/env python3
"""Bounded H3 Code6 A/B observer; not a workflow or authority.

Use only in a separately authorized native environment with independently
verified W1 archive, ELF, libraries and runtime-image custody. This observer
checks the executable digest but does not attest the surrounding environment.
"""
import argparse
import ast
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

BASE = '19cb056d48d82c856ccf703ddd69860bc0789ac8'
DRIVER = '.github/scripts/issue197_h3_migration_audit.py'
SOURCE = 'experiments/Issue1_reactor_o2plus_integration/migration_only_exact_phi_ic'
FIXTURE = 'migration_only_exact_phi_ic.i'
Q0_RUN = 'experiments/Issue31_r4_q0_all_ground/run.py'
BLOBS = {
    Q0_RUN: '626a154274d3a660d5f8c3b961a43f37c8782ecd',
    DRIVER: 'd07adea4ef644b039d77ea9b885a3cd9461bfdd6',
    SOURCE + '/' + FIXTURE: '9906040c450e28b3f1de8628c3936cf3ad1dec74',
    'physics_app/src/fvkernels/PhysicsFVMassFractionTimeDerivative.C':
        '09b0f60eb6473ac295a690e463198c370fc2870b',
    'physics_app/src/fvkernels/PhysicsFVConservativeMassFractionTimeDerivative.C':
        '177a8d74bf9806cf9000f710b6583847ae6c0c58',
}
W1_SHA = '57773f58e275f8c1c9d863a465044dab63f734bea04933b26a46459b5d743862'
INCUMBENT = 'PhysicsFVMassFractionTimeDerivative'
CANDIDATE = 'PhysicsFVConservativeMassFractionTimeDerivative'
DECK_HASHES = {
    (1, 1): 'c74f9266aec965d1db2f8396a094dc74ddcfb4224795f3301cbf85d3055cd75e',
    (1, -1): '8b1599ba690e37168444c6e3d57a750141e5d99de76f60920bd1e09af99cb631',
    (-1, 1): '6157ac08a0db8f82835e2f66d0135100a0f170c09c3ab3b5ebd68ca065e65283',
    (-1, -1): '17e6dc32aeed79bc7d9c9860da72af5ea4bc25f30704162dca75b1789698c689',
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def gitblob(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def require(condition, why):
    if not condition:
        raise RuntimeError(why)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--exe', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    root, exe, out = args.root.resolve(), args.exe.resolve(), args.out.resolve()
    require(not out.exists(), 'new output directory required')
    require(subprocess.check_output(
        ['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True
    ).strip() == BASE, 'source HEAD mismatch')
    require(not subprocess.check_output(
        ['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=no'],
        text=True).strip(), 'tracked checkout dirty')
    for path, expected in BLOBS.items():
        require(gitblob(root / path) == expected, 'source blob mismatch: ' + path)
    require(sha256(exe) == W1_SHA, 'W1 executable digest mismatch')
    sys.path.insert(0, str(root))
    from physics_harness.adapters.moose import parameters as mp
    from physics_harness.adapters.moose.nonlinear_solver import (
        failure_signature, runtime_core_facts,
    )
    from physics_harness.execution.cases import stage_case
    from physics_harness.execution.runtime import run_physics

    # The exact Q0 functions require only the execution/solver boundary.
    # Do not import the unrelated experiment and Evidence/Polars stack.
    q0_names = {'_p2', '_runtime'}
    q0_nodes = [node for node in ast.parse((root / Q0_RUN).read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name in q0_names]
    require(len(q0_nodes) == 2 and {n.name for n in q0_nodes} == q0_names,
            'Q0 runner function surface mismatch')
    q0_ns = dict(Path=Path, Any=Any, run_physics=run_physics,
                 failure_signature=failure_signature, runtime_core_facts=runtime_core_facts)
    exec(compile(ast.Module(body=q0_nodes, type_ignores=[]),
                 str(root / Q0_RUN), 'exec'), q0_ns)
    q0_run = SimpleNamespace(_p2=q0_ns['_p2'], _runtime=q0_ns['_runtime'])
    cases, logs = out / 'cases', out / 'logs'
    cases.mkdir(parents=True)
    logs.mkdir()
    names = {'sha256', 'top_float', 'replace_scalar', 'rel_err',
             'current_runtime_input', 'run_control'}
    nodes = [node for node in ast.parse((root / DRIVER).read_text()).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    require(len(nodes) == len(names) and {n.name for n in nodes} == names,
            'driver function surface mismatch')
    ns = dict(hashlib=hashlib, re=re, csv=csv, math=math, Path=Path, mp=mp,
              stage_case=stage_case, q0_run=q0_run, SOURCE=root / SOURCE,
              CASES=cases, LOGS=logs, EXE=exe, REL_FLUX_TOL=1e-3,
              REL_BALANCE_TOL=1e-8, ZERO_FLUX_ABS_TOL=1e-20, FIELD_MAGNITUDE=2e4)
    exec(compile(ast.Module(body=nodes, type_ignores=[]),
                 str(root / DRIVER), 'exec'), ns)
    original = ns['current_runtime_input']
    records = {}
    for z, field in DECK_HASHES:
        key = f'z{z:+d}_f{field:+d}'
        raw, promotions = original(charge_number=z, field_sign=field)
        require(hashlib.sha256(raw.encode()).hexdigest() == DECK_HASHES[(z, field)],
                'historical deck drift: ' + key)
        require(ns['top_float'](raw, 'rho0') == 1.0, 'fixture density drift')
        require(mp.get_parameter(raw, 'FVKernels/ion_time', 'type') == INCUMBENT,
                'unexpected incumbent')
        base = mp.upsert_parameter(raw, 'Executioner', 'scheme', 'implicit-euler')
        variant = mp.upsert_parameter(base, 'FVKernels/ion_time', 'type', CANDIDATE)
        require(mp.upsert_parameter(variant, 'FVKernels/ion_time', 'type', INCUMBENT)
                == base, 'non-type delta')
        require(mp.get_parameter(base, 'Executioner', 'scheme') == 'implicit-euler',
                'scheme assignment not retained')
        for name, deck, obj in [('A', base, INCUMBENT), ('B', variant, CANDIDATE)]:
            def build(*, charge_number, field_sign, _deck=deck, _obj=obj):
                require((charge_number, field_sign) == (z, field),
                        'pair scope changed')
                return _deck, dict(promotions, **{'FVKernels/ion_time': _obj})
            ns['current_runtime_input'] = build
            result = ns['run_control'](key + '_' + name,
                                       charge_number=z, field_sign=field)
            require(result.get('input_sha256') == hashlib.sha256(deck.encode()).hexdigest(),
                    'staged deck mismatch')
            records[key + '_' + name] = result
        a, b = records[key + '_A'], records[key + '_B']
        records[key + '_comparison'] = {
            'historical_deck_sha256': DECK_HASHES[(z, field)],
            'explicit_BE_input': True,
            'pinned_constant_density_fixture': True,
            'both_oracles_pass': a.get('pass') is True and b.get('pass') is True,
            'csv_exact_match': bool(a.get('csv_sha256')) and
                               a.get('csv_sha256') == b.get('csv_sha256'),
        }
    comparisons = [v for k, v in records.items() if k.endswith('_comparison')]
    passed = len(comparisons) == 4 and all(
        x['both_oracles_pass'] and x['csv_exact_match'] for x in comparisons)
    summary = {
        'source_head': BASE, 'binary_sha256': sha256(exe), 'pairs': records,
        'bounded_h3_ab_pass': passed, 'effective_scheme_independently_verified': False,
        'full_w1_custody_verified_by_observer': False, 'native_ad_verified': False,
        'variable_density_native_verified': False, 'safe_delete': False,
        'work_enrolled': False, 'controller_execution_approved': False,
    }
    (out / 'h3-code6-ab.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
