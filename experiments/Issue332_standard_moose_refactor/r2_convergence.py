"""Issue #334 R2: Standard-MOOSE convergence capability discriminator.

Question: can the qualified Gen34 rule
  DefaultMultiAppFixedPointConvergence AND max|delta phi| <= 1e-6 V
be represented using only standard Convergence objects while retaining Steffensen?

Pinned MOOSE SteffensenSolve::initialSetup() requires the configured
multiapp_fixed_point_convergence object to derive from
DefaultMultiAppFixedPointConvergence. ParsedConvergence does not, so the exact
standard composition is expected to be rejected before runtime.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.Issue310_fp_acceleration import control_seq34_relax2x_reference_input as gen34

g = gen34.g
GENERATED = ROOT / "generated_r2"
RESULTS = ROOT / "results_r2"
HEAVY_CYCLES = 1
FINAL_TAU = 400.0
CUSTOM = "custom_convergence_short"
PROBE = "standard_and_probe_short"

CUSTOM_BLOCK = """[Convergence]
  [gummel_delta_phi]
    type = PhysicsDeltaPhiMultiAppConvergence
    delta_phi_pp = fp_delta_phi_max
    delta_phi_abs_tol = 9.9999999999999995e-07
  []
[]
"""

STANDARD_BLOCK = """[Convergence]
  [default_fp]
    type = DefaultMultiAppFixedPointConvergence
    fixed_point_min_its = 2
    fixed_point_max_its = 3000
    fixed_point_rel_tol = 1.0e-8
    fixed_point_abs_tol = 1.0e-12
    accept_on_max_fixed_point_iteration = false
  []
  [delta_phi]
    type = PostprocessorConvergence
    postprocessor = fp_delta_phi_max
    tolerance = 9.9999999999999995e-07
  []
  [gummel_standard_and]
    type = ParsedConvergence
    convergence_expression = 'default_fp & delta_phi'
    symbol_names = 'default_fp delta_phi'
    symbol_values = 'default_fp delta_phi'
  []
[]
"""


def _bind() -> None:
    gen34.HEAVY_CYCLES = HEAVY_CYCLES
    gen34.FINAL_TAU = FINAL_TAU
    gen34._bind_clock()


def _standardize_convergence(fast: str) -> str:
    if fast.count(CUSTOM_BLOCK) != 1:
        raise RuntimeError("qualified convergence block changed")
    fast = fast.replace(CUSTOM_BLOCK, STANDARD_BLOCK, 1)
    old = "  multiapp_fixed_point_convergence = gummel_delta_phi\n"
    if fast.count(old) != 1:
        raise RuntimeError("fixed-point convergence selector changed")
    fast = fast.replace(old, "  multiapp_fixed_point_convergence = gummel_standard_and\n", 1)

    # Explicit standard convergence objects must own these parameters; remove
    # only the Executioner copies while retaining the values inside default_fp.
    exec_head, rest = fast.split("[Executioner]", 1)
    exec_body, conv_tail = rest.split("[Convergence]", 1)
    for line in (
        "  fixed_point_min_its = 2\n",
        "  fixed_point_max_its = 3000\n",
        "  fixed_point_rel_tol = 1.0e-8\n",
        "  fixed_point_abs_tol = 1.0e-12\n",
        "  accept_on_max_fixed_point_iteration = false\n",
    ):
        if exec_body.count(line) != 1:
            raise RuntimeError(f"qualified Executioner parameter anchor changed: {line.strip()}")
        exec_body = exec_body.replace(line, "", 1)
    fast = exec_head + "[Executioner]" + exec_body + "[Convergence]" + conv_tail

    if "PhysicsDeltaPhiMultiAppConvergence" in fast:
        raise RuntimeError("custom convergence remained in standard probe")
    return fast


def build(clean: bool = True) -> None:
    _bind()
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    raw = {
        "name": CUSTOM,
        "role": "optimized",
        "bandwidth": 5,
        "relaxation_factor": 0.45,
        "custom_convergence": True,
        "delta_phi_abs_tol": 1.0e-6,
        "fp_algorithm": "steffensen",
        "compute_scaling_once": True,
        "suppress_fp_anchor_output": True,
        "vector_profiles_final_only": True,
    }
    parent, fast, poisson, p = gen34._optimized_inputs(raw)
    for name, standard in ((CUSTOM, False), (PROBE, True)):
        d = GENERATED / name
        d.mkdir(parents=True, exist_ok=True)
        this_fast = _standardize_convergence(fast) if standard else fast
        (d / "input.i").write_text(parent)
        (d / "fast_sub.i").write_text(this_fast)
        (d / "poisson_sub.i").write_text(poisson)
        shutil.copy2(g.base.ELECTRON_MOMENTS, d / "electron_moments.txt")
        shutil.copy2(g.base.ELASTIC_DATA, d / "o2_elastic.txt")
        shutil.copy2(g.base.HEAVY_TRANSPORT_DATA, d / "transport_data.txt")
        (d / "case.json").write_text(json.dumps({
            **p,
            "issue": 334,
            "phase": "R2",
            "name": name,
            "standard_convergence_probe": standard,
            "heavy_cycles": 1,
            "electron_steps": 4,
        }, indent=2, sort_keys=True) + "\n")


def p0() -> None:
    build()
    a = GENERATED / CUSTOM / "fast_sub.i"
    b = GENERATED / PROBE / "fast_sub.i"
    sa, sb = a.read_text(), b.read_text()
    assert "type = PhysicsDeltaPhiMultiAppConvergence" in sa
    assert "multiapp_fixed_point_convergence = gummel_delta_phi" in sa
    assert "type = PhysicsDeltaPhiMultiAppConvergence" not in sb
    assert "type = DefaultMultiAppFixedPointConvergence" in sb
    assert "type = PostprocessorConvergence" in sb
    assert "type = ParsedConvergence" in sb
    assert "convergence_expression = 'default_fp & delta_phi'" in sb
    assert "multiapp_fixed_point_convergence = gummel_standard_and" in sb
    assert "fixed_point_algorithm = 'steffensen'" in sb
    assert "fixed_point_min_its = 2" in sb
    exec_text = sb.split("[Executioner]", 1)[1].split("[Convergence]", 1)[0]
    assert "fixed_point_min_its" not in exec_text
    print("ISSUE334_R2_P0: PASS")


def capability_probe() -> None:
    build()
    RESULTS.mkdir(parents=True, exist_ok=True)
    rel = ROOT.relative_to(REPO)
    log_rel = f"{rel}/results_r2/standard_and_probe.log"
    cmd = f"""
set -euo pipefail
source /environment
export MOOSE_DIR=/opt/physics_vendor/moose CRANE_DIR=/opt/physics_vendor/crane SQUIRREL_DIR=/opt/physics_vendor/squirrel ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt
make -C /workspace/physics_app -j2
cd /workspace/{rel}/generated_r2/{CUSTOM}
/workspace/physics_app/physics-opt --check-input -i input.i
/workspace/physics_app/physics-opt --check-input -i fast_sub.i
cd /workspace/{rel}/generated_r2/{PROBE}
set +e
/workspace/physics_app/physics-opt --check-input -i fast_sub.i > /workspace/{log_rel} 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
  timeout 60 /workspace/physics_app/physics-opt -i input.i >> /workspace/{log_rel} 2>&1
  rc=$?
fi
set -e
cat /workspace/{log_rel}
if [ "$rc" -eq 0 ]; then
  echo "Expected Steffensen/ParsedConvergence incompatibility was not reproduced" >&2
  exit 2
fi
grep -q "Only DefaultMultiAppFixedPointConvergence objects may be used" /workspace/{log_rel}
"""
    g.base._docker(cmd)
    result = {
        "issue": 334,
        "phase": "R2",
        "classification": "KEEP_CUSTOM_SEMANTICS_REQUIRED",
        "evidence_valid": True,
        "pinned_moose_sha": "9f388366ccf38b9c34542ec5561198249fde0ac9",
        "qualified_algorithm": "steffensen",
        "required_semantics": "DefaultMultiAppFixedPointConvergence AND abs(delta_phi)<=1e-6 V",
        "standard_candidate": "ParsedConvergence(DefaultMultiAppFixedPointConvergence & PostprocessorConvergence)",
        "capability_result": (
            "Rejected by pinned SteffensenSolve: multiapp_fixed_point_convergence must be "
            "DefaultMultiAppFixedPointConvergence-derived."
        ),
        "why_default_only_is_insufficient": (
            "DefaultMultiAppFixedPointConvergence combines residual and custom_pp checks with OR, "
            "while the qualified custom class requires residual convergence first and then delta-phi."
        ),
        "decision": (
            "Retain PhysicsDeltaPhiMultiAppConvergence for the qualified Steffensen endpoint. "
            "Do not weaken AND semantics to obtain a standard-only input."
        ),
    }
    (RESULTS / "r2_capability_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE334_R2_CAPABILITY:", json.dumps(result, sort_keys=True))


def case() -> None:
    path = RESULTS / "r2_capability_summary.json"
    if not path.exists():
        raise SystemExit("R2 capability summary missing from prepared bundle")
    result = json.loads(path.read_text())
    assert result["classification"] == "KEEP_CUSTOM_SEMANTICS_REQUIRED"
    assert result["evidence_valid"] is True
    print("ISSUE334_R2_CASE:", json.dumps(result, sort_keys=True))


def aggregate() -> None:
    root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT required")
    found = []
    for p in Path(root).rglob("r2_capability_summary.json"):
        found.append(json.loads(p.read_text()))
    if not found:
        raise SystemExit("R2 capability evidence missing")
    result = found[0]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "r2_terminal.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("ISSUE334_R2_AGGREGATE:", json.dumps(result, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--case", action="store_true")
    ap.add_argument("--aggregate", action="store_true")
    a = ap.parse_args()
    if a.p0: p0()
    elif a.probe: capability_probe()
    elif a.case: case()
    elif a.aggregate: aggregate()
    else: ap.error("choose action")


if __name__ == "__main__":
    main()
