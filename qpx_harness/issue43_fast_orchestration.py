"""Guarded Issue43 scientific orchestration for the fast-plasma discriminator."""
from __future__ import annotations

from . import issue43_fast_contract as _contract_owner
from . import issue43_fast_output_execution as _output
for _name in dir(_output):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_output, _name)

_RAW_CLASSIFY = relaxation_recipe.classify
_RAW_WRITE_CONTRACT_ARTIFACTS = _write_contract_artifacts


def _write_contract_artifacts_isolated(**kwargs: Any) -> dict[str, str]:
    forwarded = dict(kwargs)
    measurements_root = Path(forwarded["measurements_root"])
    forwarded["measurements_root"] = measurements_root / "execution_contracts"
    return _RAW_WRITE_CONTRACT_ARTIFACTS(**forwarded)


def _install_artifact_namespace() -> None:
    # _run_case_safe is defined in the contract owner, so its mutable dispatch
    # point must be updated in that defining module rather than in this module.
    _contract_owner._CONTRACT_ARTIFACT_WRITER = _write_contract_artifacts_isolated


def _harness_decision(label: str, case: dict[str, Any] | None) -> dict[str, Any] | None:
    if case is None or case.get("class") != "HARNESS_OR_CONSTRUCTION_FAIL":
        return None
    contract = case.get("execution_contract_p3") or case.get("execution_contract_p1")
    decision: dict[str, Any] = {
        "class": "HARNESS_OR_CONSTRUCTION_FAIL",
        "reason": f"{label} failed execution/ontology conformance before physics classification",
        "failed_case": label,
    }
    if isinstance(contract, dict):
        decision["contract_status"] = contract.get("status")
        decision["contract_blockers"] = contract.get("blockers")
    return decision


def _guarded_classify(
    known_good: dict[str, Any],
    electron_300k: dict[str, Any] | None,
    oneway: dict[str, Any] | None,
    feedback_base: dict[str, Any] | None,
    feedback_small: dict[str, Any] | None,
    feedback_large: dict[str, Any] | None,
    tau_dr: float,
) -> dict[str, Any]:
    for label, case in (
        ("electron_300K", electron_300k),
        ("oneway_e_to_phi", oneway),
        ("feedback_base", feedback_base),
        ("feedback_small", feedback_small),
        ("feedback_large", feedback_large),
    ):
        guarded = _harness_decision(label, case)
        if guarded is not None:
            return guarded

    return _RAW_CLASSIFY(
        known_good,
        electron_300k,
        oneway,
        feedback_base,
        feedback_small,
        feedback_large,
        tau_dr,
    )


def _ontology_blocked(case: dict[str, Any] | None) -> bool:
    return case is not None and case.get("class") == "HARNESS_OR_CONSTRUCTION_FAIL"


def _contract_signature(case: dict[str, Any] | None) -> str:
    if case is None:
        return "not-run"
    p1 = case.get("execution_contract_p1")
    p3 = case.get("execution_contract_p3")
    p1_status = p1.get("status") if isinstance(p1, dict) else "n/a"
    p3_status = p3.get("status") if isinstance(p3, dict) else "n/a"
    return f"P1={p1_status} P3={p3_status}"


def _v4_compat_self_test() -> int:
    try:
        if _v3_compat_self_test() != 0:
            raise AssertionError("v3 compatibility self-test failed")

        with tempfile.TemporaryDirectory() as tmp:
            measurements_root = Path(tmp) / "measurements"
            case_id = "ownership_probe"
            paths = _write_contract_artifacts_isolated(
                measurements_root=measurements_root,
                case_id=case_id,
                contract={"schema_version": 1},
                p1={"status": "PASS"},
                p3=None,
            )
            legacy_owned = measurements_root / case_id
            isolated = measurements_root / "execution_contracts" / case_id
            if legacy_owned.exists():
                raise AssertionError(
                    "contract writer created legacy runner-owned measurement path"
                )
            if not isolated.is_dir():
                raise AssertionError("isolated contract artifact directory was not created")
            if Path(paths["contract"]).parent != isolated:
                raise AssertionError("contract artifact path escaped isolated namespace")

        kge = {"class": "P3_PASS", "canonical_checker": {"status": "PASS"}}
        harness = {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "execution_contract_p1": {
                "status": "HOLD",
                "blockers": [{"id": "dt-above-dtmin"}],
            },
        }
        decision = _guarded_classify(kge, harness, None, None, None, None, 1.0e-12)
        if decision.get("class") != "HARNESS_OR_CONSTRUCTION_FAIL":
            raise AssertionError("construction failure was relabeled as physics failure")
        if not _ontology_blocked(harness):
            raise AssertionError("ontology failure did not prune dependent branches")
        good = {"class": "P3_PASS", "analysis": {"status": "PASS"}}
        decision = _guarded_classify(kge, good, good, good, None, good, 1.0e-12)
        if decision.get("class") != "FEEDBACK_IMPLICIT_COUPLING_RECOVERS_NEAR_TAU_DR":
            raise AssertionError("positive scientific classification path changed")
    except Exception as exc:
        print(f"ISSUE43_FAST_V4_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE43_FAST_V4_SELFTEST: PASS")
    return 0


def _run_issue43_guarded(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Issue43 CORE-16-aware electron/Poisson coupling discriminator"
    )
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _v4_compat_self_test()
    if _v4_compat_self_test() != 0:
        return 1

    _install_artifact_namespace()

    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / issue43_runtime.BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise SystemExit(f"missing accepted qvt electron control: {base_case}")

    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    results_root = (
        Path(args.results_root).expanduser().resolve()
        if args.results_root
        else exe.parent / "temp" / "results"
    )
    root = _create_root(results_root)
    root = root.with_name(
        root.name.replace("fast_plasma_relaxation_", "fast_plasma_discriminator_v4_")
    )
    original = next(
        (
            p
            for p in root.parent.glob(
                root.name.replace(
                    "fast_plasma_discriminator_v4_", "fast_plasma_relaxation_"
                )
                + "*"
            )
        ),
        None,
    )
    if not root.exists() and original is not None and original.is_dir():
        original.rename(root)
    root.mkdir(parents=True, exist_ok=True)
    cases_root = root / "cases"
    measurements_root = root / "measurements"
    cases_root.mkdir(exist_ok=True)
    measurements_root.mkdir(exist_ok=True)

    mesh = scale_audit.mesh_stats(base_case / "qvt.msh")
    scales = scale_audit.anchor_scales(
        pressure=scale_audit.DEFAULT_PRESSURE,
        gas_temperature=issue43_runtime.GAS_TEMPERATURE,
        electron_density=scale_audit.DEFAULT_ELECTRON_DENSITY,
        mu_n=scale_audit.DEFAULT_MU_N,
        d_n=scale_audit.DEFAULT_D_N,
        dt=issue43_runtime.HEAVY_MACRO_DT,
        mesh=mesh,
        rf_frequency=None,
    )
    tau_dr = float(scales["electron"]["dielectric_relaxation_s"])
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()

    known_good = issue43_runtime.run_known_good(
        repo_root=repo_root,
        exe=exe,
        cases_root=cases_root,
        measurements_root=measurements_root,
    )
    if (
        known_good.get("class") != "P3_PASS"
        or known_good.get("canonical_checker", {}).get("status") != "PASS"
    ):
        decision = _guarded_classify(known_good, None, None, None, None, None, tau_dr)
        summary_path = root / "summary.json"
        _write_json(
            summary_path,
            {"scale_map": scales, "known_good": known_good, "decision": decision},
        )
        print(f"ISSUE43_FAST2_PRECLASS: {decision['class']}")
        print(f"ISSUE43_FAST2_REASON: {decision['reason']}")
        print(f"ISSUE43_FAST2_SUMMARY: {summary_path}")
        return 2

    e300_text = _build_electron_v5(
        base_text,
        dt=issue43_runtime.DT_ELECTRON_CONTROL,
        steps=issue43_runtime.N_STEPS,
    )
    electron_300k = _run_case_v5(
        base_case=base_case,
        case_dir=cases_root / "electron_300K",
        input_text=e300_text,
        case_id="Issue43_FAST2_electron_300K",
        exe=exe,
        measurements_root=measurements_root,
        analyze=False,
    )

    oneway = None
    feedback_base = None
    feedback_small = None
    feedback_large = None

    if not _ontology_blocked(electron_300k) and issue43_runtime.physics_pass(electron_300k):
        oneway_text = _build_oneway_v5(
            base_text,
            dt=issue43_runtime.DT_ELECTRON_CONTROL,
            steps=issue43_runtime.N_STEPS,
            radial_span=radial_span,
        )
        oneway = _run_case_v5(
            base_case=base_case,
            case_dir=cases_root / "oneway_e_to_phi",
            input_text=oneway_text,
            case_id="Issue43_FAST2_oneway_e_to_phi",
            exe=exe,
            measurements_root=measurements_root,
            analyze=True,
        )

    if (
        oneway is not None
        and not _ontology_blocked(oneway)
        and issue43_runtime.physics_pass(oneway)
    ):
        feedback_text = _build_feedback_v5(
            base_text,
            dt=issue43_runtime.DT_FEEDBACK_BASE,
            steps=issue43_runtime.N_STEPS,
            radial_span=radial_span,
        )
        feedback_base = _run_case_v5(
            base_case=base_case,
            case_dir=cases_root / "feedback_dt1e13",
            input_text=feedback_text,
            case_id="Issue43_FAST2_feedback_dt1e13",
            exe=exe,
            measurements_root=measurements_root,
            analyze=True,
        )

        if not _ontology_blocked(feedback_base):
            if issue43_runtime.physics_pass(feedback_base):
                large_text = _build_feedback_v5(
                    base_text,
                    dt=issue43_runtime.DT_FEEDBACK_LARGE,
                    steps=issue43_runtime.N_STEPS,
                    radial_span=radial_span,
                )
                feedback_large = _run_case_v5(
                    base_case=base_case,
                    case_dir=cases_root / "feedback_dt1e12",
                    input_text=large_text,
                    case_id="Issue43_FAST2_feedback_dt1e12",
                    exe=exe,
                    measurements_root=measurements_root,
                    analyze=True,
                )
            else:
                small_text = _build_feedback_v5(
                    base_text,
                    dt=issue43_runtime.DT_FEEDBACK_SMALL,
                    steps=issue43_runtime.N_STEPS,
                    radial_span=radial_span,
                )
                feedback_small = _run_case_v5(
                    base_case=base_case,
                    case_dir=cases_root / "feedback_dt1e14",
                    input_text=small_text,
                    case_id="Issue43_FAST2_feedback_dt1e14",
                    exe=exe,
                    measurements_root=measurements_root,
                    analyze=True,
                )

    decision = _guarded_classify(
        known_good,
        electron_300k,
        oneway,
        feedback_base,
        feedback_small,
        feedback_large,
        tau_dr,
    )
    summary = {
        "scale_map": scales,
        "dt_over_tau_dr": {
            "electron_control": issue43_runtime.DT_ELECTRON_CONTROL / tau_dr,
            "feedback_base": issue43_runtime.DT_FEEDBACK_BASE / tau_dr,
            "feedback_small": issue43_runtime.DT_FEEDBACK_SMALL / tau_dr,
            "feedback_large": issue43_runtime.DT_FEEDBACK_LARGE / tau_dr,
        },
        "known_good": known_good,
        "electron_300k": electron_300k,
        "oneway": oneway,
        "feedback_base": feedback_base,
        "feedback_small": feedback_small,
        "feedback_large": feedback_large,
        "decision": decision,
    }
    summary_path = root / "summary.json"
    _write_json(summary_path, summary)

    print(f"ISSUE43_FAST2_KGE: {known_good.get('class')}")
    print(
        f"ISSUE43_FAST2_E300: {electron_300k.get('class')} "
        f"contract={_contract_signature(electron_300k)}"
    )
    if oneway is not None:
        print(
            f"ISSUE43_FAST2_ONEWAY: {oneway.get('class')} "
            f"contract={_contract_signature(oneway)}"
        )
    if feedback_base is not None:
        print(
            f"ISSUE43_FAST2_FEEDBACK_1E13: {feedback_base.get('class')} "
            f"contract={_contract_signature(feedback_base)}"
        )
        print(
            "ISSUE43_FAST2_FEEDBACK_1E13_RESIDUAL: "
            f"{feedback_base.get('nonlinear_residual_summary')}"
        )
    if feedback_small is not None:
        print(
            f"ISSUE43_FAST2_FEEDBACK_1E14: {feedback_small.get('class')} "
            f"contract={_contract_signature(feedback_small)}"
        )
        print(
            "ISSUE43_FAST2_FEEDBACK_1E14_RESIDUAL: "
            f"{feedback_small.get('nonlinear_residual_summary')}"
        )
    if feedback_large is not None:
        print(
            f"ISSUE43_FAST2_FEEDBACK_1E12: {feedback_large.get('class')} "
            f"contract={_contract_signature(feedback_large)}"
        )
        print(
            "ISSUE43_FAST2_FEEDBACK_1E12_RESIDUAL: "
            f"{feedback_large.get('nonlinear_residual_summary')}"
        )
    print(f"ISSUE43_FAST2_PRECLASS: {decision['class']}")
    print(f"ISSUE43_FAST2_REASON: {decision['reason']}")
    print(f"ISSUE43_FAST2_SUMMARY: {summary_path}")

    failure_classes = {
        "KNOWN_GOOD_ELECTRON_CONTROL_FAIL",
        "ELECTRON_300K_CONTROL_FAIL",
        "POISSON_OR_BLOCK_SCALING_FAIL",
        "FEEDBACK_JACOBIAN_SCALING_OR_INITIALIZATION_FAIL",
        "HARNESS_OR_CONSTRUCTION_FAIL",
        "FEEDBACK_CASE_MISSING",
    }
    return 2 if decision["class"] in failure_classes else 0


__all__ = [name for name in globals() if not name.startswith("__")]
