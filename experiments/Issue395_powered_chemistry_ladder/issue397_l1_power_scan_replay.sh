#!/usr/bin/env bash
# Canonical Issue 397 graded coarse L1 replay; migrated from historical
# GitHub Actions workflow to a Samuel-governed experiment stage script.
# No workflow file is installed by this script. The source case commands,
# Maxwell exact-change audit, native D1 gates and archive provenance are retained.
set -euo pipefail
PHASE="${1:?usage: bash issue397_l1_power_scan_replay.sh prepare|build|check|solve|audit 200|250|300}"
POWER_W="${2:?RF target 200, 250, 300, 600 or 1000 W is required}"
# The fixed historical power allowlist remains byte-identical in its control
# branch. Only the opt-in 400 W research case bypasses that allowlist.
if [[ "$POWER_W" = 400 && "${OXYGEN_RESEARCH_400:-0}" = 1 ]]; then
  :
else
  case "$POWER_W" in 200|250|300|600|1000) ;; *) echo "unsupported RF target: $POWER_W" >&2; exit 2 ;; esac
fi
case "$PHASE" in prepare|build|check|solve|audit) ;; *) echo "unsupported phase: $PHASE" >&2; exit 2 ;; esac
test "$(git rev-parse --show-toplevel)" = "$PWD" || {
  echo "run the replay from the exact repository checkout root" >&2; exit 2;
}
if [[ -n "${CHATGPT_WORK_BASE_SHA:-}" ]]; then
  test "$(git rev-parse HEAD)" = "$CHATGPT_WORK_BASE_SHA" || {
    echo "governed-work exact-source SHA mismatch" >&2; exit 2;
  }
fi
# Canonical experiment.yml checks out control/ and target/ separately: mount the
# actual pinned target Git root, never the parent Actions workspace.
export GITHUB_WORKSPACE="$PWD"
export MODE=B DT_NS=1000
export BUILD_BASE_REF=ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008
export CHEM=experiments/Issue395_powered_chemistry_ladder
export DIEL=experiments/Issue3_dielectric_surface_charge
export BASE=experiments/fem_fvm_plasma_discriminator
export TABLE=experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt
export RESULT="$CHEM/results_rf_elastic_diss_ion_ei20_ei01_${POWER_W}w_adjacent_sheath_wall_closed_100us_dt${DT_NS}ns"
export INPUT="$CHEM/rf_elastic_diss_ion_ei20_ei01_${POWER_W}w_adjacent_sheath_wall_closed_100us_dt${DT_NS}ns.i"
export PARENT="$CHEM/rf_elastic_multiapp_parent_${POWER_W}w_100us_dt${DT_NS}ns_overlay.i"
export CHILD_OVERLAY="$CHEM/rf_elastic_multiapp_maxwell_${POWER_W}w_100us_dt${DT_NS}ns_overlay.i"
export CHILD_INPUT="$CHEM/rf_elastic_multiapp_maxwell_${POWER_W}w_100us_dt${DT_NS}ns_child.i"
export ELASTIC="$CHEM/o2_elastic_${POWER_W}w_100us_dt${DT_NS}ns_overlay.i"
export DISS="$CHEM/o2_dissociation_${POWER_W}w_100us_dt${DT_NS}ns_overlay.i"
export ION="$CHEM/o2_ionization_${POWER_W}w_100us_dt${DT_NS}ns_overlay.i"
export ION_O="$CHEM/o_ionization_ei20_${POWER_W}w_100us_dt${DT_NS}ns_overlay.i"
export ATTACH="$CHEM/o2_attachment_ei01_${POWER_W}w_100us_dt${DT_NS}ns_overlay.i"
export OELASTIC="$CHEM/o_elastic_ei17_${POWER_W}w_100us_dt${DT_NS}ns_overlay.i"
# Optional NEW research-only EI407/413/414 -> O2(a) lumped source.
# Off by default. Historical validated 200/250/300/600/1000W replays unchanged.
export O2A_LUMPED="$CHEM/o2a_lumped_ei407_413_414_${POWER_W}w_100us_dt${DT_NS}ns_overlay.i"
export O2A_EXTRA_INPUT=''
export EI2738_OVERLAY="$CHEM/ei2738_detachment_formula_${POWER_W}w_100us_dt${DT_NS}ns_overlay.i"
export EI2738_EXTRA_INPUT=''
if [[ "${OXYGEN_RESEARCH_EI2738_FORMULA:-0}" = 1 ]]; then
  EI2738_EXTRA_INPUT="'$EI2738_OVERLAY'"
fi
# Full 24-channel experimental case: exactly ONE chemistry overlay owns
# all 19 electron lookup, two formula and three heavy reaction progress rates.
export FULL24_OVERLAY="$CHEM/full24_${POWER_W}w_100us_dt${DT_NS}ns_overlay.i"
export CHEM_SOURCE_INPUTS="'$DISS' '$ION' '$ION_O' '$ATTACH'"
export FULL24_EXTRA_INPUT=''
if [[ "${OXYGEN_RESEARCH_FULL24:-0}" = 1 ]]; then
  test -n "${OXYGEN_RESEARCH_RATE_DIR:-}" || {
    echo "OXYGEN_RESEARCH_FULL24 needs private 19 lookup files" >&2; exit 2;
  }
  test "${OXYGEN_RESEARCH_LUMPED_O2A:-0}" != 1 && \
  test "${OXYGEN_RESEARCH_EI2738_FORMULA:-0}" != 1 || {
    echo "FULL24 cannot run simultaneously with prior partial EI overlays" >&2; exit 2;
  }
  # Full24 subsumes partial 401/415/dissociation/O2a/2738 owners.
  CHEM_SOURCE_INPUTS="'$FULL24_OVERLAY'"
fi
if [[ "${OXYGEN_RESEARCH_LUMPED_O2A:-0}" = 1 ]]; then
  test -n "${OXYGEN_RESEARCH_RATE_DIR:-}" || {
    echo "OXYGEN_RESEARCH_RATE_DIR with three 100-point lookups is required" >&2; exit 2;
  }
  O2A_EXTRA_INPUT="'$O2A_LUMPED'"
fi
echo "ISSUE397_REPLAY_PHASE=$PHASE TARGET_W=$POWER_W SOURCE_SHA=$(git rev-parse HEAD)"
case "$PHASE" in
  prepare)
set -euo pipefail
python3 -m py_compile "$CHEM/issue397_d1_instrument.py" "$CHEM/issue397_d1_analyze.py" "$CHEM/issue397_materialize_l1_baseline.py" "$CHEM/issue397_build_graded_mesh.py" "$CHEM/issue397_graded_mesh_geometry.py" "$CHEM/issue397_graded_mesh_quality.py"
python3 "$CHEM/issue397_d1_instrument.py" --self-test
python3 "$CHEM/issue397_d1_analyze.py" --self-test
rm -rf "$RESULT"
mkdir -p "$RESULT/prep" "$RESULT/run"

python3 "$BASE/generate_contour_mesh.py" > "$RESULT/prep/mesh_plasma.log" 2>&1
python3 "$DIEL/extend_cover_mesh.py" \
  "$BASE/plasma_contour_l3_4p5mm.msh" "$DIEL/baseline_cover_fine_source.msh" \
  > "$RESULT/prep/mesh_cover.log" 2>&1
python3 "$DIEL/build_unstructured_cover_wafer_mesh.py" \
  "$DIEL/baseline_cover_fine_source.msh" "$DIEL/baseline_plasma_plus_unstructured_cover_plus_wafer.msh" \
  > "$RESULT/prep/mesh_cover_wafer.log" 2>&1
python3 "$DIEL/add_focus_ring_block.py" \
  "$DIEL/baseline_plasma_plus_unstructured_cover_plus_wafer.msh" "$DIEL/baseline_plasma_plus_unstructured_cover_plus_wafer.msh" \
  > "$RESULT/prep/mesh_focus.log" 2>&1
python3 "$DIEL/add_vacuum_coils_block.py" \
  "$DIEL/baseline_plasma_plus_unstructured_cover_plus_wafer.msh" "$DIEL/baseline_plasma_plus_unstructured_cover_plus_wafer.msh" \
  > "$RESULT/prep/mesh_vacuum.log" 2>&1

cp "$DIEL/baseline_plasma_plus_unstructured_cover_plus_wafer.msh" "$RESULT/prep/mesh_before_refinement.msh"
# Canonical Issue397 graded-coarse L1, pinned by mesh SHA + 27 wafer faces.
python3 "$CHEM/issue397_materialize_l1_baseline.py" \
  "$DIEL/baseline_plasma_plus_unstructured_cover_plus_wafer.msh" \
  "$CHEM/baseline_plasma_plus_unstructured_cover_plus_wafer.msh" \
  | tee "$RESULT/prep/graded_L1_baseline_mesh.log"
grep -q "ISSUE397_BASELINE_L1_MESH_PASS" "$RESULT/prep/graded_L1_baseline_mesh.log"
cp "$CHEM/baseline_plasma_plus_unstructured_cover_plus_wafer.msh" \
  "$RESULT/prep/mesh_after_refinement.msh"
cp "$CHEM/baseline_plasma_plus_unstructured_cover_plus_wafer.msh" \
  "$RESULT/prep/graded_level_1.msh"
python3 "$DIEL/prepare_baseline_cover_pilot.py" "$CHEM/a0_full_icp.i" > "$RESULT/prep/materialize.log" 2>&1
python3 "$DIEL/finalize_baseline_cover_pilot.py" "$CHEM/a0_full_icp.i" > "$RESULT/prep/finalize.log" 2>&1
python3 "$DIEL/promote_cover_wafer_15us.py" "$CHEM/a0_full_icp.i" > "$RESULT/prep/wafer.log" 2>&1
python3 "$DIEL/promote_focus_ring_15us.py" "$CHEM/a0_full_icp.i" > "$RESULT/prep/focus.log" 2>&1
python3 "$DIEL/promote_vacuum_coils_15us.py" "$CHEM/a0_full_icp.i" > "$RESULT/prep/vacuum.log" 2>&1

cp "$CHEM/a0_full_icp.i" "$INPUT"
python3 "$DIEL/promote_cover_15us.py" "$INPUT" > "$RESULT/prep/original_timegrid.log" 2>&1
python3 "$CHEM/set_timegrid_100us_460steps.py" "$INPUT" | tee "$RESULT/prep/timegrid_460.log"
python3 "$CHEM/enable_electron_adjacent_sheath_wall.py" "$INPUT" \
  | tee "$RESULT/prep/electron_adjacent_sheath_wall.log"

python3 - "$INPUT" <<'PY' | tee "$RESULT/prep/inlet_outlet_charged_closed.log"
import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding='utf-8')
block_re = re.compile(r'(?ms)^  \[(?P<name>[^\]\n]+)\]\n(?P<body>.*?)^  \[\]\n')
blocks = {m.group('name'): m.group('body') for m in block_re.finditer(text)}
for name, variable in {'ion_wall':'log_ni','negative_ion_wall':'log_nm','atomic_positive_ion_wall':'log_nop'}.items():
    body = blocks.get(name)
    if body is None or 'type = FVFunctorNeumannBC' not in body or f'variable = {variable}' not in body:
        raise SystemExit(f'{name}: canonical wall BC contract missing')
    m = re.search(r"(?m)^\s*boundary\s*=\s*'([^']+)'\s*$", body)
    if m is None or not {'inlet','outlet'}.issubset(set(m.group(1).split())):
        raise SystemExit(f'{name}: inlet/outlet not closed')
print('ISSUE395_INLET_OUTLET_CHARGED_CLOSED_PASS')
PY

python3 "$CHEM/build_rf_multiapp_coupling_power.py" \
  --target-w "$POWER_W" \
  --table "$TABLE" \
  --parent-overlay "$PARENT" \
  --child-overlay "$CHILD_OVERLAY" \
  --child-input "$CHILD_INPUT" \
  | tee "$RESULT/prep/multiapp_power.log"

# Generate a byte-identical Maxwell source except for nl_abs_tol; never edit the shared reference.
python3 - "$CHILD_INPUT" "$RESULT/prep/maxwell_tolerance.json" <<'PY'
from pathlib import Path
import hashlib, json, sys
child, audit = (Path(v) for v in sys.argv[1:])
original = Path("experiments/Issue202_maxwell_scalar_fem_m0/rf_power.i").read_text(encoding="utf-8")
old, new = "  nl_abs_tol = 1e-12\n", "  nl_abs_tol = 1e-11\n"
assert original.count(old) == 1, "Unexpected Maxwell baseline source"
assert original.count("  nl_rel_tol = 1e-10\n") == 1
assert original.count("  nl_max_its = 20\n") == 1
patched = original.replace(old, new)
assert patched.replace(new, old) == original
patched_path = child.parent / "issue397_maxwell_steady_abs1e11.i"
patched_path.write_text(patched, encoding="utf-8")
prior = child.read_text(encoding="utf-8")
a = "!include ../Issue202_maxwell_scalar_fem_m0/rf_power.i\n"
b = "!include issue397_maxwell_steady_abs1e11.i\n"
assert prior.count(a) == 1
child.write_text(prior.replace(a,b), encoding="utf-8")
digest = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()
audit.write_text(json.dumps({"one_change": "Maxwell Steady nl_abs_tol",
    "baseline_sha256": digest(original), "variant_sha256": digest(patched),
    "before": 1e-12, "after": 1e-11, "rel_tol": 1e-10,
    "max_newton_its": 20, "PID_max_drive_unmodified": 3.0}, indent=2)+"\n")
print("ISSUE397_MAXWELL_SINGLE_TOLERANCE_CHANGE_PASS")
PY

cp physics_app/data/electron_impact/o2_elastic.txt "$CHEM/o2_elastic.txt"
python3 "$CHEM/build_o2_elastic_overlay.py" \
  --base-input "$CHEM/a0_full_icp.i" \
  --output "$ELASTIC" \
  --elastic-table o2_elastic.txt \
  | tee "$RESULT/prep/elastic_overlay.log"

python3 "$CHEM/build_o2_dissociation_overlay.py" \
  --base-input "$CHEM/a0_full_icp.i" \
  --output "$DISS" \
  | tee "$RESULT/prep/dissociation_overlay.log"

cp physics_app/data/electron_impact/o2_ionization.txt "$CHEM/o2_ionization.txt"
python3 "$CHEM/build_o2_ionization_overlay.py" \
  --base-input "$CHEM/a0_full_icp.i" \
  --output "$ION" \
  --ei16-table o2_ionization.txt \
  | tee "$RESULT/prep/o2_ionization_overlay.log"

cp physics_app/data/electron_impact/o_ionization.txt "$CHEM/o_ionization.txt"
python3 "$CHEM/build_o_ionization_overlay.py" \
  --base-input "$CHEM/a0_full_icp.i" \
  --output "$ION_O" \
  --ei20-table o_ionization.txt \
  | tee "$RESULT/prep/o_ionization_ei20_overlay.log"

cp physics_app/data/electron_impact/o2_attachment.txt "$CHEM/o2_attachment.txt"
python3 "$CHEM/build_o2_attachment_overlay.py" \
  --base-input "$CHEM/a0_full_icp.i" \
  --output "$ATTACH" \
  --attachment-table o2_attachment.txt \
  | tee "$RESULT/prep/o2_attachment_ei01_overlay.log"

cp physics_app/data/electron_impact/o_elastic.txt "$CHEM/o_elastic.txt"
python3 "$CHEM/build_o_elastic_overlay.py" \
  --base-input "$CHEM/a0_full_icp.i" \
  --output "$OELASTIC" \
  --elastic-table o_elastic.txt \
  --source-table physics_app/data/electron_impact/o_elastic.txt \
  | tee "$RESULT/prep/o_elastic_ei17_overlay.log"

python3 "$CHEM/check_wafer_checkerboard_ab.py" "$INPUT" --mode "$MODE" \
  | tee "$RESULT/prep/wafer_checkerboard_AB.log"
python3 "$CHEM/issue397_d1_instrument.py" --self-test | tee "$RESULT/prep/d1_instrument_selftest.log"
python3 "$CHEM/issue397_d1_analyze.py" --self-test | tee "$RESULT/prep/d1_analyzer_selftest.log"
python3 "$CHEM/issue397_d1_instrument.py" "$INPUT" | tee "$RESULT/prep/d1_native_instrument.log"
# Case B reference: wafer O2+, O+, O- all keep original thermal+migration.
# Electron retains the canonical adjacent-electrode sheath law.
# Rebuild the *canonical* 100-us / 460-step grid: historical B/D1
# instrumentation intentionally truncated it to 60/2 us before this step.
python3 "$CHEM/set_timegrid_100us_460steps.py" "$INPUT" \
  | tee "$RESULT/prep/final_100us_timegrid.log"
grep -q "ISSUE395_TIMEGRID_100US_460STEPS_PASS" "$RESULT/prep/final_100us_timegrid.log"
grep -q "total_steps=460" "$RESULT/prep/final_100us_timegrid.log"
# Exact archived L1 mesh identity and baseline manifest must agree.
grep -q "ISSUE397_BASELINE_L1_MESH_PASS" "$RESULT/prep/graded_L1_baseline_mesh.log"
python3 "$CHEM/issue397_materialize_l1_baseline.py" \
  --verify-existing "$CHEM/baseline_plasma_plus_unstructured_cover_plus_wafer.msh" \
  | tee "$RESULT/prep/graded_L1_baseline_verify.log"
grep -q "ISSUE397_BASELINE_L1_MESH_PASS" "$RESULT/prep/graded_L1_baseline_verify.log"
! grep -q "use_bohm_ion_collection = true" "$INPUT"
! grep -q "use_negative_ion_sheath_barrier = true" "$INPUT"
grep -q "negative_ion_wall_number_flux" "$INPUT"
grep -q "atomic_positive_ion_wall_number_flux" "$INPUT"
grep -q "ion_wall_number_flux" "$INPUT"
grep -q 'ISSUE397_D1_NATIVE_DIAGNOSTICS_INPUT_PASS' "$RESULT/prep/d1_native_instrument.log"
grep -q 'type = PhysicsWaferD1GeometryProbeAux' "$INPUT"
grep -q 'type = PhysicsLowerDSurfaceCurrentProbeAux' "$INPUT"

python3 -m py_compile \
  "$CHEM/issue397_d1_instrument.py" \
  "$CHEM/issue397_materialize_l1_baseline.py" \
  "$CHEM/issue397_graded_mesh_geometry.py" \
  "$CHEM/issue397_graded_mesh_quality.py" \
  "$CHEM/issue397_build_graded_mesh.py" \
  "$CHEM/issue397_d1_analyze.py" \
  "$CHEM/check_wafer_checkerboard_ab.py" \
  "$CHEM/set_timegrid_100us_460steps.py" \
  "$CHEM/build_o_elastic_overlay.py" \
  "$CHEM/enable_electron_adjacent_sheath_wall.py" \
  "$CHEM/build_rf_multiapp_coupling_power.py" \
  "$CHEM/build_o2_elastic_overlay.py" \
  "$CHEM/build_o2_dissociation_overlay.py" \
  "$CHEM/build_o2_ionization_overlay.py" \
  "$CHEM/build_o_ionization_overlay.py" \
  "$CHEM/build_o2_attachment_overlay.py"

EXPECTED_STEPS=460
grep -q 'ISSUE395_TIMEGRID_100US_460STEPS_PASS' "$RESULT/prep/timegrid_460.log"
grep -q 'segment_0_to_100_ns_dt=1ns_steps=100' "$RESULT/prep/timegrid_460.log"
grep -q 'segment_100_to_2000_ns_dt=10ns_steps=190' "$RESULT/prep/timegrid_460.log"
grep -q 'segment_2000_to_10000_ns_dt=100ns_steps=80' "$RESULT/prep/timegrid_460.log"
grep -q "segment_10000_to_100000_ns_dt=1000ns_steps=90" "$RESULT/prep/timegrid_460.log"
grep -q "total_steps=$EXPECTED_STEPS" "$RESULT/prep/timegrid_460.log"
grep -q "ISSUE395_WAFER_CHECKERBOARD_TEST_${MODE}_INPUT_PASS" "$RESULT/prep/wafer_checkerboard_AB.log"
grep -q 'type = PhysicsLowerDSurfaceCurrentProbeAux' "$INPUT"
if [ "$MODE" = A ]; then
  grep -A5 '^  \[wafer_surface_current\]' "$INPUT" | grep -q "expression = '0.25'"
else
  grep -A8 '^  \[wafer_surface_current\]' "$INPUT" | grep -Fq "expression = '1.602176634e-19*(gi+gop-gm-ge)'"
fi
grep -q 'ISSUE397_BASELINE_L1_MESH_PASS' "$RESULT/prep/graded_L1_baseline_mesh.log"
grep -q 'ISSUE395_EI17_O_ELASTIC_OVERLAY_BUILD_PASS' "$RESULT/prep/o_elastic_ei17_overlay.log"
grep -q 'reaction_progress = R_elastic_O' "$OELASTIC"
grep -q 'rate_table_file = o_elastic.txt' "$OELASTIC"
grep -q 'variable = log_energy' "$OELASTIC"
test "$(grep -c 'reaction_progress = R_elastic_O' "$OELASTIC")" -eq 1
grep -q 'ISSUE395_INLET_OUTLET_CHARGED_CLOSED_PASS' "$RESULT/prep/inlet_outlet_charged_closed.log"
grep -q 'ISSUE395_ELECTRON_ADJACENT_SHEATH_WALL_PASS' "$RESULT/prep/electron_adjacent_sheath_wall.log"
grep -q 'ISSUE395_RF_MULTIAPP_POWER_BUILD_PASS' "$RESULT/prep/multiapp_power.log"
test -s "$RESULT/prep/maxwell_tolerance.json"
grep -q 'nl_abs_tol = 1e-11' "$CHEM/issue397_maxwell_steady_abs1e11.i"
grep -q '^!include issue397_maxwell_steady_abs1e11[.]i$' "$CHILD_INPUT"
grep -q "target_W=${POWER_W}" "$RESULT/prep/multiapp_power.log"
grep -Eq "target = ${POWER_W}(\\.0+)?$" "$PARENT"
grep -q 'R_elastic_O2' "$ELASTIC"
grep -q 'R_diss_O2' "$DISS"
grep -q 'R_ion_O2' "$ION"
grep -q 'R_ion_O' "$ION_O"
grep -q 'rate_table_file = o_ionization.txt' "$ION_O"
grep -q 'variable = log_nop' "$ION_O"
grep -q 'variable = w_O' "$ION_O"
grep -q '13.618' "$ION_O"
grep -q 'ISSUE395_EI01_ONLY_OVERLAY_BUILD_PASS' "$RESULT/prep/o2_attachment_ei01_overlay.log"
grep -q 'reaction_progress = R_attachment' "$ATTACH"
grep -q 'rate_table_file = o2_attachment.txt' "$ATTACH"
grep -q 'variable = log_nm' "$ATTACH"
grep -q 'variable = log_ne' "$ATTACH"
grep -q 'variable = w_O' "$ATTACH"
grep -q 'S_heavy_mass_closure_EI01' "$ATTACH"
grep -q 'S_charge_molar_closure_EI01' "$ATTACH"
test "$(grep -c 'reaction_progress = R_attachment' "$ATTACH")" -eq 1
if [[ "${OXYGEN_RESEARCH_LUMPED_O2A:-0}" = 1 ]]; then
  python3 "$CHEM/build_lumped_o2a_ei407_413_414.py" \
    --base-input "$INPUT" \
    --rate-dir "$OXYGEN_RESEARCH_RATE_DIR" \
    --output "$O2A_LUMPED" \
    | tee "$RESULT/prep/o2a_lumped_EI407_413_414.log"
  test -s "$O2A_LUMPED" || { echo "missing O2a lumped overlay" >&2; exit 2; }
  for rid in 407 413 414; do
    grep -q "reaction_progress = R_EI$rid" "$O2A_LUMPED"
    test -s "$CHEM/private_rates/EI-$rid"_O2_X.txt
  done
fi
if [[ "${OXYGEN_RESEARCH_EI2738_FORMULA:-0}" = 1 ]]; then
  python3 "$CHEM/build_ei2738_detachment_formula_overlay.py" \
    --base-input "$INPUT" \
    --output "$EI2738_OVERLAY" \
    | tee "$RESULT/prep/ei2738_detachment_formula.log"
  test -s "$EI2738_OVERLAY" || { echo "EI2738 Formula overlay missing" >&2; exit 2; }
  grep -q 'property_name = R_EI2738' "$EI2738_OVERLAY"
fi
if [[ "${OXYGEN_RESEARCH_FULL24:-0}" = 1 ]]; then
  # The 200sccm inlet is a research modification, never overwrite old baseline.
  python3 "$CHEM/build_oxygen_icp_200sccm_inlet.py" \
    --base-input "$INPUT" --output "$INPUT.full24_tmp"
  mv "$INPUT.full24_tmp" "$INPUT"
  python3 "$CHEM/apply_oxygen_24_initial_seeds.py" \
    --base-input "$INPUT" --output "$INPUT.seed_tmp"
  mv "$INPUT.seed_tmp" "$INPUT"
  python3 "$CHEM/build_oxygen_24_wall_overlay.py" \
    --base-input "$INPUT" --output "$INPUT.wall_tmp" \
    | tee "$RESULT/prep/full24_wall_sticking1.log"
  mv "$INPUT.wall_tmp" "$INPUT"
  python3 "$CHEM/build_oxygen_24_source_overlay.py" \
    --base-input "$INPUT" \
    --rate-dir "$OXYGEN_RESEARCH_RATE_DIR" \
    --root "$PWD" --output "$FULL24_OVERLAY" \
    | tee "$RESULT/prep/full24_source_overlay.log"
  grep -q 'OXYGEN_25_OEX_CHEMISTRY_OVERLAY_PREPARED_NOT_RUN' \
    "$RESULT/prep/full24_source_overlay.log"
  test -s "$FULL24_OVERLAY"
  # P0: number fractions are derived from the neutral mass-fraction ICs.
  # Reject inherited 10%-level neutral densities before any external solve.
  python3 "$CHEM/apply_oxygen_24_initial_seeds.py" --self-test \
    | tee "$RESULT/prep/full24_neutral_seed_p0_selftest.log"
  python3 "$CHEM/apply_oxygen_24_initial_seeds.py" --check-input "$INPUT" \
    | tee "$RESULT/prep/full24_neutral_seed_p0.log"
  grep -q OXYGEN24_INITIAL_SEED_P0_PASS "$RESULT/prep/full24_neutral_seed_p0.log"
  # P0: MOOSE Parser reserves x,y,z,t,pi,e. Reject invalid generated
  # ParsedFunctorMaterial aliases before Docker build or physics-opt P2.
  python3 bin/physics.py preflight --self-test \
    | tee "$RESULT/prep/full24_parser_preflight_selftest.log"
  python3 bin/physics.py preflight "$FULL24_OVERLAY" \
    | tee "$RESULT/prep/full24_parser_preflight.log"
fi
# Opt-in 2-ns, 2-step P3 smoke; canonical 100us/460-step preflight remains above.
# Only full24 research. This verifies short-run construction, not 100us chemistry.
if [[ "${OXYGEN_RESEARCH_QUICK_5MIN:-0}" = 1 ]]; then
  test "${OXYGEN_RESEARCH_FULL24:-0}" = 1 || { echo "quick mode requires full24" >&2; exit 2; }
  python3 "$CHEM/set_timegrid_oxygen24_2ns_smoke.py" --self-test \
    | tee "$RESULT/prep/full24_smoke_timegrid_selftest.log"
  python3 "$CHEM/set_timegrid_oxygen24_2ns_smoke.py" "$INPUT" \
    | tee "$RESULT/prep/full24_smoke_timegrid.log"
  python3 "$CHEM/set_timegrid_oxygen24_2ns_smoke.py" --verify "$INPUT" \
    | tee "$RESULT/prep/full24_smoke_timegrid_verified.log"
  grep -q OXYGEN24_SMOKE_2NS_TIMEGRID_PASS "$RESULT/prep/full24_smoke_timegrid_verified.log"
  python3 "$CHEM/apply_oxygen_24_initial_seeds.py" --check-input "$INPUT" \
    | tee "$RESULT/prep/full24_neutral_seed_after_smoke.log"
fi
    ;;
  build)
docker pull "$BUILD_BASE_REF"
set -euo pipefail
docker run --rm --entrypoint /bin/bash --user 0:0 \
  --workdir /workspace -v "$GITHUB_WORKSPACE:/workspace" \
  "$BUILD_BASE_REF" -lc '
    set -euo pipefail
    source /environment
    git config --global --add safe.directory /workspace
    git config --global --add safe.directory /opt/physics_vendor/moose
    git config --global --add safe.directory /opt/physics_vendor/crane
    git config --global --add safe.directory /opt/physics_vendor/squirrel
    git config --global --add safe.directory /opt/physics_vendor/zapdos
    export MOOSE_DIR=/opt/physics_vendor/moose
    export CRANE_DIR=/opt/physics_vendor/crane
    export SQUIRREL_DIR=/opt/physics_vendor/squirrel
    export ZAPDOS_DIR=/opt/physics_vendor/zapdos
    export METHOD=opt
    make -C physics_app -j2
  '
test -x physics_app/physics-opt
    ;;
  check)
set -euo pipefail
if [[ "${OXYGEN_RESEARCH_LUMPED_O2A:-0}" = 1 ]]; then
  test -s "$O2A_LUMPED" || { echo "O2a overlay not prepared" >&2; exit 2; }
fi
docker run --rm --entrypoint /bin/bash --user 0:0 \
  --workdir /workspace -v "$GITHUB_WORKSPACE:/workspace" \
  "$BUILD_BASE_REF" -lc "
    set -euo pipefail
    source /environment
    physics_app/physics-opt --check-input \
      -i '$INPUT' \
      '$PARENT' \
      '$ELASTIC' \
      ${CHEM_SOURCE_INPUTS} \
      '$OELASTIC' ${O2A_EXTRA_INPUT} ${EI2738_EXTRA_INPUT}
  " 2>&1 | tee "$RESULT/check_input.log"
    ;;
  solve)
set -euo pipefail
if [[ "${OXYGEN_RESEARCH_LUMPED_O2A:-0}" = 1 ]]; then
  test -s "$O2A_LUMPED" || { echo "O2a overlay not prepared" >&2; exit 2; }
fi
docker run --rm --entrypoint /bin/bash --user 0:0 \
  --workdir /workspace -v "$GITHUB_WORKSPACE:/workspace" \
  "$BUILD_BASE_REF" -lc "
    set -euo pipefail
    source /environment
    physics_app/physics-opt \
      -i '$INPUT' \
      '$PARENT' \
      '$ELASTIC' \
      ${CHEM_SOURCE_INPUTS} \
      '$OELASTIC' \
      Outputs/file_base='$RESULT/run/plasma' ${O2A_EXTRA_INPUT} ${EI2738_EXTRA_INPUT}
  " 2>&1 | tee "$RESULT/runtime.log"
    ;;
  audit)
set -euo pipefail
python3 "$CHEM/issue397_d1_analyze.py" \
  --input "$RESULT/run/plasma.e" \
  --output "$RESULT/d1_native" \
  | tee "$RESULT/d1_native_analysis.log"
grep -q "D1_NATIVE_DIAGNOSTIC_INTEGRITY_PASS" "$RESULT/d1_native_analysis.log"
    ;;
esac
echo "ISSUE397_REPLAY_PHASE_PASS=$PHASE TARGET_W=$POWER_W"
