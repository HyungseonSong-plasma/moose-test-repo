#!/usr/bin/env python3
"""Issue #306 Sequence 06: 300-cycle thermal chi10 vs Bohm chi100 comparison."""
from __future__ import annotations
from contextlib import contextmanager
import argparse, json, os, shutil, subprocess, sys, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT))
from experiments.Issue306_heavy_charge_motion import control as base
from experiments.Issue306_heavy_charge_motion import wall03_control as wall03
from experiments.Issue306_heavy_charge_motion import wall05_control as wall05

ROOT=Path(__file__).resolve().parent; REPO=ROOT.parents[1]
GENERATED=ROOT/'generated_wall06'; RESULTS=ROOT/'results_wall06'
CYCLES=300; CHI_H=40.0
SPECS=(
 {'name':'thermal_chi10_cycles300','mode':'thermal','chi':10.0,'fp_max':300},
 {'name':'bohm_chi100_cycles300','mode':'comsol','chi':100.0,'fp_max':3000},
)
CASE_NAMES=tuple(x['name'] for x in SPECS)

@contextmanager
def horizon():
 old_c,old_f=base.HEAVY_CYCLES,base.FINAL_TAU
 try:
  base.HEAVY_CYCLES=CYCLES; base.FINAL_TAU=CHI_H*CYCLES; yield
 finally: base.HEAVY_CYCLES=old_c; base.FINAL_TAU=old_f

def params(spec):
 with horizon(): p=wall03._params(spec)
 return p

def build(clean=True):
 if clean and GENERATED.exists(): shutil.rmtree(GENERATED)
 GENERATED.mkdir(parents=True,exist_ok=True); built=[]
 for spec in SPECS:
  p=params(spec); d=GENERATED/p['name']; d.mkdir(parents=True,exist_ok=True)
  with horizon(): parent=wall03._parent(p); fast=wall03._fast(p); poisson=base._poisson_child()
  (d/'input.i').write_text(parent); (d/'fast_sub.i').write_text(fast); (d/'poisson_sub.i').write_text(poisson)
  shutil.copy2(base.ELECTRON_MOMENTS,d/'electron_moments.txt'); shutil.copy2(base.ELASTIC_DATA,d/'o2_elastic.txt'); shutil.copy2(base.HEAVY_TRANSPORT_DATA,d/'transport_data.txt')
  (d/'case.json').write_text(json.dumps(p,indent=2,sort_keys=True)+'\n'); built.append(p)
 (GENERATED/'matrix.json').write_text(json.dumps({'issue':306,'sequence':6,'heavy_cycles':300,'chi_h':40.0,'cases':built},indent=2)+'\n')
 return built

def p0():
 built=build()
 assert [p['name'] for p in built]==list(CASE_NAMES)
 assert [float(p['chi_e']) for p in built]==[10.0,100.0]
 assert all(int(p['heavy_cycles'])==300 for p in built)
 assert built[0]['positive_ion_surface_model']=='thermal_sticking'
 assert built[1]['positive_ion_surface_model']=='bohm'
 for p in built:
  parent=(GENERATED/p['name']/'input.i').read_text(); fast=(GENERATED/p['name']/'fast_sub.i').read_text()
  assert 'num_steps = 300' in parent and 'boundary = left' in parent and 'boundary = right' in parent
  assert '0.5*exp(loge)' in fast and '[right_energy_surface_loss]' in fast
 print('ISSUE306_WALL06_P0: PASS')

def p1():
 build(); rel=ROOT.relative_to(REPO)
 cmds='; '.join(f'python3 /workspace/bin/physics.py preflight /workspace/{rel}/generated_wall06/{n}/input.i' for n in CASE_NAMES)
 base._docker('set -euo pipefail; source /environment; export PYTHONPATH=/workspace; uv pip install --system --python "$(command -v python3)" -r /workspace/requirements-evidence-engine.txt; python3 /workspace/bin/physics.py preflight --self-test; '+cmds)
 print('ISSUE306_WALL06_P1: PASS')

def p2():
 if not GENERATED.exists(): build()
 rel=ROOT.relative_to(REPO); checks=[]
 for n in CASE_NAMES:
  checks += [f'cd /workspace/{rel}/generated_wall06/{n} && /workspace/physics_app/physics-opt --check-input -i input.i',f'cd /workspace/{rel}/generated_wall06/{n} && /workspace/physics_app/physics-opt --check-input -i fast_sub.i']
 base._docker('set -euo pipefail; source /environment; export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt; make -C /workspace/physics_app -j2; '+'; '.join(checks))
 print('ISSUE306_WALL06_P2: PASS')

def inner_run(name):
 RESULTS.mkdir(parents=True,exist_ok=True); d=GENERATED/name; t=time.perf_counter()
 with (RESULTS/f'{name}_runtime.log').open('w') as h: r=subprocess.run([str(REPO/'physics_app'/'physics-opt'),'-i','input.i'],cwd=d,stdout=h,stderr=subprocess.STDOUT)
 (RESULTS/f'{name}_returncode.txt').write_text(str(r.returncode)+'\n'); (RESULTS/f'{name}_elapsed_seconds.txt').write_text(f'{time.perf_counter()-t:.9f}\n'); return 0

def analyze(name):
 p=json.loads((GENERATED/name/'case.json').read_text()); oldg,oldr=base.GENERATED,base.RESULTS
 try:
  base.GENERATED,base.RESULTS=GENERATED,RESULTS
  with horizon(): result,code=base.analyze_case(name)
 finally: base.GENERATED,base.RESULTS=oldg,oldr
 result.update(mode=p['mode'],flow_inlet=p['flow_inlet'],wall_boundary=p['wall_boundary'],positive_ion_surface_model=p['positive_ion_surface_model'])
 return result,code

def run_case(name):
 rel=ROOT.relative_to(REPO)
 base._docker('set -euo pipefail; source /environment; export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt PYTHONPATH=/workspace; '+f'python3 /workspace/{rel}/wall06_control.py --inner-run {name}')
 result,code=analyze(name); (RESULTS/f'{name}_result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 if code: raise SystemExit(code)

def aggregate(root):
 found={}
 for path in root.rglob('*_result.json'):
  x=json.loads(path.read_text()); n=str(x.get('case',''))
  if n in CASE_NAMES: found[n]=x
 missing=[n for n in CASE_NAMES if n not in found]
 if missing: raise RuntimeError(f'missing wall06 results: {missing}')
 a,b=found[CASE_NAMES[0]],found[CASE_NAMES[1]]
 cmp=wall05._comparison(a,b)
 return {'issue':306,'sequence':6,'classification':'THERMAL_CHI10_VS_BOHM_CHI100_COMPLETE','evidence_valid':all(bool(x.get('evidence_valid')) for x in found.values()),'heavy_cycles':300,'cases':found,'comparison_bohm_chi100_vs_thermal_chi10':cmp,'interpretation_guard':'Use offset_removed_potential_einf together with raw_potential_einf and E/net-charge metrics to distinguish a DC-level shift from a profile-shape change.'}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--phase',choices=('p0','p1','p2')); ap.add_argument('--case',choices=CASE_NAMES); ap.add_argument('--inner-run',choices=CASE_NAMES); ap.add_argument('--aggregate',action='store_true'); a=ap.parse_args(); RESULTS.mkdir(parents=True,exist_ok=True)
 if a.inner_run: return inner_run(a.inner_run)
 if a.case: run_case(a.case); return 0
 if a.aggregate:
  root=os.environ.get('CHATGPT_MATRIX_EVIDENCE_ROOT');
  if not root: raise SystemExit('CHATGPT_MATRIX_EVIDENCE_ROOT is required')
  s=aggregate(Path(root)); (RESULTS/'issue306_wall06_summary.json').write_text(json.dumps(s,indent=2,sort_keys=True)+'\n'); print(json.dumps(s,indent=2,sort_keys=True)); return 0 if s['evidence_valid'] else 2
 if a.phase: {'p0':p0,'p1':p1,'p2':p2}[a.phase](); return 0
 ap.error('one action required')
if __name__=='__main__': raise SystemExit(main())
