"""Historical v3 compatibility characterization for Issue43 fast-plasma."""
from __future__ import annotations

from . import issue43_fast_contract as _contract
for _name in dir(_contract):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_contract, _name)

# The historical self-test evaluates these aliases at call time.
_RAW_BUILD_ONEWAY = _build_oneway_fixed
_RAW_BUILD_FEEDBACK = _build_feedback_fixed


def _v3_compat_self_test() -> int:
    try:
        if issue43_runtime.self_test() != 0:
            raise AssertionError("Issue43 runtime self-test failed")
        if ec.self_test() != 0:
            raise AssertionError("execution-contract self-test failed")
        if moose_executioner.self_test() != 0:
            raise AssertionError("generic Executioner self-test failed")
        if temporal.self_test() != 0:
            raise AssertionError("generic temporal observation self-test failed")

        if _BASE_BUILD_ONEWAY is not issue43_runtime.build_oneway:
            raise AssertionError("one-way base builder alias drifted")
        if _BASE_BUILD_FEEDBACK is not issue43_runtime.build_feedback:
            raise AssertionError("feedback base builder alias drifted")
        if _RAW_BUILD_ONEWAY is not _build_oneway_fixed:
            raise AssertionError("one-way fixed-layer alias drifted")
        if _RAW_BUILD_FEEDBACK is not _build_feedback_fixed:
            raise AssertionError("feedback fixed-layer alias drifted")
        if "_RAW_BUILD_ONEWAY" in _build_oneway_fixed.__code__.co_names:
            raise AssertionError("one-way fixed builder can recurse through downstream alias")
        if "_RAW_BUILD_FEEDBACK" in _build_feedback_fixed.__code__.co_names:
            raise AssertionError("feedback fixed builder can recurse through downstream alias")

        fixture = issue43_runtime._fixture()
        for label, constructed in (
            (
                "oneway",
                _build_oneway_fixed(
                    fixture,
                    dt=issue43_runtime.DT_FEEDBACK_BASE,
                    steps=issue43_runtime.N_STEPS,
                    radial_span=0.243,
                ),
            ),
            (
                "feedback",
                _build_feedback_fixed(
                    fixture,
                    dt=issue43_runtime.DT_FEEDBACK_BASE,
                    steps=issue43_runtime.N_STEPS,
                    radial_span=0.243,
                ),
            ),
        ):
            builder_controls = _executioner_controls(constructed)
            if builder_controls.get("num_steps") != issue43_runtime.N_STEPS:
                raise AssertionError(f"{label} fixed builder lost num_steps contract")
            if not math.isclose(
                float(builder_controls.get("dt")),
                issue43_runtime.DT_FEEDBACK_BASE,
                rel_tol=1.0e-15,
                abs_tol=0.0,
            ):
                raise AssertionError(f"{label} fixed builder lost dt contract")

        base = """[Executioner]
  type = Transient
  scheme = implicit-euler
  dt = 1e-8
  end_time = 2e-8
  compute_scaling_once = true
[]
"""
        tuned = apply_micro_time_contract(base, dt=1.0e-13, steps=5)
        controls = _executioner_controls(tuned)
        required = {
            "dt": 1.0e-13,
            "end_time": 5.0e-13,
            "num_steps": 5,
            "dtmin": 1.0e-14,
            "timestep_tolerance": 1.0e-16,
            "abort_on_solve_fail": True,
        }
        for name, expected in required.items():
            actual = controls.get(name)
            if isinstance(expected, float):
                if not math.isclose(
                    float(actual), expected, rel_tol=1.0e-15, abs_tol=0.0
                ):
                    raise AssertionError(
                        f"wrong {name}: expected {expected}, got {actual}"
                    )
            elif actual != expected:
                raise AssertionError(
                    f"wrong {name}: expected {expected}, got {actual}"
                )

        contract = _build_execution_contract(
            "Issue43_FAST2_feedback_dt1e13", tuned
        )
        if ec.evaluate_contract(contract, phase="P1")["status"] != "PASS":
            raise AssertionError("valid fixed-step ontology contract failed P1")

        invalid = _set_executioner_parameter(tuned, "dtmin", "1e-12")
        invalid_contract = _build_execution_contract(
            "Issue43_FAST2_feedback_dt1e13_bad", invalid
        )
        if ec.evaluate_contract(invalid_contract, phase="P1")["status"] != "HOLD":
            raise AssertionError("dt<dtmin mutation was not rejected by ontology P1")

        duplicate = tuned.replace(
            "  num_steps = 5\n", "  num_steps = 5\n  num_steps = 6\n"
        )
        try:
            apply_micro_time_contract(duplicate, dt=1.0e-13, steps=5)
        except FastPlasmaV3Error:
            pass
        else:
            raise AssertionError("duplicate Executioner parameter was not rejected")

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            csv_path = case_dir / "input_out.csv"
            csv_path.write_text(
                "time,value\n"
                "0,0\n"
                "1e-13,1\n"
                "2e-13,1\n"
                "3e-13,1\n"
                "4e-13,1\n"
                "5e-13,1\n"
            )
            observed = _runtime_observation(case_dir)
            runtime_contract = _build_execution_contract(
                "Issue43_FAST2_feedback_dt1e13", tuned
            )
            runtime_contract["runtime_regime"]["observed"].update(observed)
            runtime_contract["evidence"]["observed"]["p3_returncode"] = 0
            if ec.evaluate_contract(runtime_contract, phase="P3")["status"] != "PASS":
                raise AssertionError("valid runtime trajectory failed ontology P3")

            csv_path.write_text("time,value\n0,0\n")
            zero_observed = _runtime_observation(case_dir)
            zero_contract = _build_execution_contract(
                "Issue43_FAST2_feedback_dt1e13_zero", tuned
            )
            zero_contract["runtime_regime"]["observed"].update(zero_observed)
            zero_contract["evidence"]["observed"]["p3_returncode"] = 0
            if ec.evaluate_contract(zero_contract, phase="P3")["status"] != "HOLD":
                raise AssertionError("initial-only runtime was not held by ontology P3")
    except Exception as exc:
        print(f"ISSUE43_FAST_V3_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE43_FAST_V3_SELFTEST: PASS")
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
