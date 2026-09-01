"""Final Issue43/Issue44 compatibility characterization for the fast runtime."""
from __future__ import annotations

from . import issue43_fast_orchestration as _orchestration
for _name in dir(_orchestration):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_orchestration, _name)


def self_test() -> int:
    try:
        if _v4_compat_self_test() != 0:
            raise AssertionError("absorbed v4 self-test failed")
        if ooc.self_test() != 0:
            raise AssertionError("output-observation contract self-test failed")

        base = """[Executioner]
  type = Transient
  dt = 1e-14
  end_time = 5e-14
  num_steps = 5
  dtmin = 1e-15
  timestep_tolerance = 1e-17
  abort_on_solve_fail = true
[]
[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
"""
        tuned = ooc.apply_microtime_output_contract(base, dt=1.0e-14)
        report = ooc.observation_report(tuned, required_time_separation=1.0e-14)
        if ooc.evaluate_observation_report(report)["status"] != "PASS":
            raise AssertionError("valid observation report did not pass")
        augmented = _augment_execution_contract("Issue44_output_contract_probe", tuned)
        if ec.evaluate_contract(augmented, phase="P1")["status"] != "PASS":
            raise AssertionError("valid output-aware execution contract failed P1")

        mutated = ooc._set_parameter(
            tuned, "Outputs/out", "new_row_tolerance", "1e-12"
        )
        bad_report = ooc.observation_report(
            mutated, required_time_separation=1.0e-14
        )
        if ooc.evaluate_observation_report(bad_report)["status"] != "HOLD":
            raise AssertionError("historical output-row suppression mutation was not rejected")
        bad_contract = _augment_execution_contract("Issue44_output_contract_bad", mutated)
        if ec.evaluate_contract(bad_contract, phase="P1")["status"] != "HOLD":
            raise AssertionError("execution contract did not reject output-row suppression")

        check_args = _p2_check_input_args()
        if "--check-input" not in check_args or "--show-outputs" in check_args:
            raise AssertionError("P2 check-input arguments are not phase isolated")
        if "--no-color" in check_args or check_args[-2:] != ("--color", "off"):
            raise AssertionError("P2 check-input did not use current color CLI contract")

        introspection_args = _p2_output_introspection_args()
        if "--show-outputs" not in introspection_args:
            raise AssertionError("output introspection did not request --show-outputs")
        if "--check-input" in introspection_args:
            raise AssertionError("output introspection leaked check-input early exit")
        if "Executioner/num_steps=0" not in introspection_args:
            raise AssertionError("output introspection lacks zero-step phase guard")

        complete_trajectory = {
            "status": "PASS",
            "time_steps_seen": 5,
            "converged_steps": 5,
            "solver_final_time": 5.0e-14,
        }
        good_runtime = _evaluate_output_runtime_confirmation(
            returncode=0,
            trajectory=complete_trajectory,
            csv_times=[0.0, 1e-14, 2e-14, 3e-14, 4e-14, 5e-14],
            dt=1.0e-14,
            steps=5,
            row_tolerance=1.0e-17,
        )
        if (
            good_runtime["status"] != "PASS"
            or good_runtime["class"] != "OUTPUT_OBSERVATION_CONTRACT_PASS"
        ):
            raise AssertionError("valid runtime row-identity evidence failed")

        suppressed_runtime = _evaluate_output_runtime_confirmation(
            returncode=0,
            trajectory=complete_trajectory,
            csv_times=[0.0],
            dt=1.0e-14,
            steps=5,
            row_tolerance=1.0e-17,
        )
        if (
            suppressed_runtime["status"] != "HOLD"
            or suppressed_runtime["class"] != "OUTPUT_OBSERVATION_CONTRACT_FAIL"
        ):
            raise AssertionError("suppressed runtime rows were accepted")

        shifted_runtime = _evaluate_output_runtime_confirmation(
            returncode=0,
            trajectory=complete_trajectory,
            csv_times=[0.0, 2e-14, 3e-14, 4e-14, 5e-14, 6e-14],
            dt=1.0e-14,
            steps=5,
            row_tolerance=1.0e-17,
        )
        if shifted_runtime["status"] != "HOLD":
            raise AssertionError("shifted runtime row identities were accepted")

        incomplete_runtime = _evaluate_output_runtime_confirmation(
            returncode=1,
            trajectory={
                "status": "PASS",
                "time_steps_seen": 1,
                "converged_steps": 0,
                "solver_final_time": 1.0e-14,
            },
            csv_times=[0.0],
            dt=1.0e-14,
            steps=5,
            row_tolerance=1.0e-17,
        )
        if (
            incomplete_runtime["class"] != "RUNTIME_CONFIRMATION_INCONCLUSIVE"
            or incomplete_runtime["status"] != "HOLD"
        ):
            raise AssertionError("incomplete solver run was mislabeled as output failure")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log = tmp_path / "p3_runtime.log"
            log.write_text(
                "Time Step 1, time = 1e-14, dt = 1e-14\n"
                " Solve Converged!\n"
                "Time Step 2, time = 2e-14, dt = 1e-14\n"
                " Solve Converged!\n"
            )
            trajectory = _solver_trajectory(log)
            if trajectory.get("converged_steps") != 2:
                raise AssertionError("solver trajectory parser lost converged steps")
            if trajectory.get("solver_final_time") != 2.0e-14:
                raise AssertionError("solver trajectory parser lost final time")

            introspection_log = tmp_path / "introspection.log"
            introspection_log.write_text(
                "Outputs:\n"
                " out                      \"INITIAL TIMESTEP_END\"\n"
                " console                  \"INITIAL TIMESTEP_BEGIN LINEAR NONLINEAR FAILED TIMESTEP_END\"\n"
                "Time Step 0, time = 0\n"
            )
            good_framework = _framework_output_evidence(
                introspection_log,
                report,
                check_input_returncode=0,
                introspection_returncode=0,
            )
            if good_framework["status"] != "PASS":
                raise AssertionError("valid zero-step framework introspection failed")
            if good_framework.get("positive_time_steps"):
                raise AssertionError("zero-step introspection fabricated a physical timestep")

            introspection_log.write_text(
                "Outputs:\n"
                " out                      \"INITIAL\"\n"
                " console                  \"INITIAL TIMESTEP_END\"\n"
                "Time Step 0, time = 0\n"
            )
            missing_schedule = _framework_output_evidence(
                introspection_log,
                report,
                check_input_returncode=0,
                introspection_returncode=0,
            )
            failed_ids = {item["id"] for item in missing_schedule["blockers"]}
            if (
                missing_schedule["status"] != "HOLD"
                or "show-outputs-csv-timestep-end" not in failed_ids
            ):
                raise AssertionError("missing CSV TIMESTEP_END schedule was accepted")

            introspection_log.write_text(
                "Outputs:\n"
                " out                      \"INITIAL TIMESTEP_END\"\n"
                " console                  \"INITIAL TIMESTEP_END\"\n"
                "Time Step 1, time = 1e-14, dt = 1e-14\n"
            )
            phase_leak = _framework_output_evidence(
                introspection_log,
                report,
                check_input_returncode=0,
                introspection_returncode=0,
            )
            failed_ids = {item["id"] for item in phase_leak["blockers"]}
            if (
                phase_leak["status"] != "HOLD"
                or "output-introspection-no-physical-timestep" not in failed_ids
                or phase_leak.get("positive_time_steps") != [1]
            ):
                raise AssertionError("physical-timestep introspection leak was not rejected")

            p2_error = tmp_path / "p2_error.log"
            p2_error.write_text(
                "*** ERROR ***\n"
                "input.i:480.5: unused parameter 'Outputs/console/precision'\n"
            )
            p2_class = _classify_p2_failure(p2_error, 1)
            if (
                p2_class["class"] != "HARNESS_OR_CONSTRUCTION_FAIL"
                or p2_class["reason"] != "UNUSED_PARAMETER"
                or p2_class["detail"] != "Outputs/console/precision"
            ):
                raise AssertionError("P2 unused-parameter failure was not classified")
    except Exception as exc:
        print(f"ISSUE44_OUTPUT_CONTRACT_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE44_OUTPUT_CONTRACT_SELFTEST: PASS")
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
