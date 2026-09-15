#!/usr/bin/env python3
"""Issue-236 discriminator: frozen electrons with coupled heavy + Poisson solve.

This deliberately removes the MultiApp/sub-cycling path. Electron density and
electron energy are frozen at their production initial conditions as FV aux
variables. The nonlinear system contains the heavy-fluid/heavy-species
variables plus potential_plasma, and advances five equal steps over 10 ns.

The purpose is narrow: determine whether ion/heavy evolution coupled directly
to Poisson, without electron redistribution, produces the expected potential
topology. Exodus is emitted at every heavy step for spatial inspection.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run as base


TOTAL_TIME_S = 1.0e-8
HEAVY_STEPS = 5
HEAVY_DT_S = TOTAL_TIME_S / HEAVY_STEPS

FROZEN_ELECTRON_VARIABLES = ("n_e", "n_epsilon")
POISSON_VARIABLE = "potential_plasma"
SOLVER_VARIABLES = (*base.HEAVY_SOLVER_VARIABLES, POISSON_VARIABLE)

_ROOT_ASSIGNMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
_PP_REF_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*_pp)\s*=\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)"
)


def _strip_hit_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    out: list[str] = []
    for char in line:
        if escaped:
            out.append(char)
            escaped = False
            continue
        if char == "\\":
            out.append(char)
            escaped = True
            continue
        if quote is not None:
            out.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            out.append(char)
            continue
        if char == "#":
            break
        out.append(char)
    return "".join(out)


def _root_assignment_table(text: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, line in enumerate(text.splitlines(keepends=True)):
        raw = line.rstrip("\r\n")
        if not raw or raw[0].isspace() or raw.lstrip().startswith("#"):
            continue
        match = _ROOT_ASSIGNMENT_RE.fullmatch(_strip_hit_comment(raw).rstrip())
        if not match:
            continue
        name, rhs = match.groups()
        if name in result:
            raise base.Issue236Error(f"duplicate root assignment: {name}")
        result[name] = {"line_index": index, "rhs": rhs}
    return result


def _mentions_symbol(text: str, name: str) -> bool:
    return (
        re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text)
        is not None
    )


def _root_liveness(text: str) -> dict[str, Any]:
    roots = _root_assignment_table(text)
    names = set(roots)
    dependencies: dict[str, set[str]] = {name: set() for name in names}
    for name, entry in roots.items():
        rhs = str(entry["rhs"])
        dependencies[name] = {
            other for other in names if other != name and _mentions_symbol(rhs, other)
        }

    assignment_lines = {int(entry["line_index"]) for entry in roots.values()}
    live: set[str] = set()
    for index, line in enumerate(text.splitlines()):
        if index in assignment_lines:
            continue
        code = _strip_hit_comment(line)
        for name in names:
            if _mentions_symbol(code, name):
                live.add(name)

    pending = list(live)
    while pending:
        name = pending.pop()
        for dependency in dependencies[name]:
            if dependency not in live:
                live.add(dependency)
                pending.append(dependency)

    dead = names - live
    return {
        "root_parameters": sorted(names),
        "live_root_parameters": sorted(live),
        "dead_root_parameters": sorted(dead),
        "dependencies": {
            name: sorted(dependencies[name]) for name in sorted(dependencies)
        },
    }


def _prune_dead_root_parameters(text: str) -> tuple[str, dict[str, Any]]:
    before = _root_liveness(text)
    dead = set(before["dead_root_parameters"])
    if not dead:
        return text, {"before": before, "after": before, "removed": []}

    roots = _root_assignment_table(text)
    dead_lines = {int(roots[name]["line_index"]) for name in dead}
    lines = text.splitlines(keepends=True)
    pruned = "".join(line for index, line in enumerate(lines) if index not in dead_lines)
    after = _root_liveness(pruned)
    if after["dead_root_parameters"]:
        raise base.Issue236Error(
            f"root-parameter pruning did not reach closure: {after['dead_root_parameters']}"
        )
    return pruned, {"before": before, "after": after, "removed": sorted(dead)}


def _postprocessor_references(text: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for line in text.splitlines():
        match = _PP_REF_RE.match(_strip_hit_comment(line))
        if match:
            parameter, target = match.groups()
            refs.append({"parameter": parameter, "target": target})
    return refs


def _missing_postprocessor_references(text: str) -> list[str]:
    return sorted(
        {
            ref["target"]
            for ref in _postprocessor_references(text)
            if not base.mb.has_block(text, f"Postprocessors/{ref['target']}")
        }
    )


def _owned_variables(text: str, section: str) -> list[str]:
    result: list[str] = []
    for path in base._children(text, section):
        variable = base.mp.unquote(base.mp.get_parameter(text, path, "variable"))
        if variable:
            result.append(variable)
    return result


def _build_heavy_poisson_input(production_text: str) -> str:
    variable_names = {
        base._name(path) for path in base._children(production_text, "Variables")
    }
    if variable_names != base.EXPECTED_VARIABLES:
        raise base.Issue236Error(
            f"unexpected production variable set: {sorted(variable_names)}; "
            f"expected {sorted(base.EXPECTED_VARIABLES)}"
        )

    text = base._move_variables_to_aux(
        production_text, FROZEN_ELECTRON_VARIABLES
    )

    # Remove electron particle/energy equations only. Poisson remains nonlinear
    # and is solved together with the heavy system.
    text, removed_electron_bcs = base._remove_equations_owned_by(
        text, set(FROZEN_ELECTRON_VARIABLES)
    )
    text = base._remove_postprocessors_for_missing_bcs(
        text, removed_electron_bcs
    )

    # MultiApp/transfer objects are not part of this discriminator.
    text = base._remove_top_if_present(text, "MultiApps")
    text = base._remove_top_if_present(text, "Transfers")

    # Vector diagnostics are not needed for the topology discriminator and can
    # carry ownership dependencies from the removed electron equations.
    text = base._remove_top_if_present(text, "VectorPostprocessors")

    text = base.mp.upsert_parameter(text, "Problem", "solve", "true")
    text = base.mp.upsert_parameter(
        text, "Executioner", "dt", f"{HEAVY_DT_S:.17g}"
    )
    text = base.mp.upsert_parameter(
        text, "Executioner", "end_time", f"{TOTAL_TIME_S:.17g}"
    )

    if base.mb.has_block(text, "Outputs"):
        text = base.mp.upsert_parameter(text, "Outputs", "exodus", "true")
        text = base.mp.upsert_parameter(text, "Outputs", "csv", "true")
        text = base.mp.upsert_parameter(
            text, "Outputs", "execute_on", "'INITIAL TIMESTEP_END FINAL'"
        )

    text, _ = _prune_dead_root_parameters(text)
    return text


def _audit_input(text: str) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    for name in base.HEAVY_SOLVER_VARIABLES:
        checks[f"heavy_solver:{name}"] = base.mb.has_block(
            text, f"Variables/{name}"
        )
        checks[f"heavy_not_aux:{name}"] = not base.mb.has_block(
            text, f"AuxVariables/{name}"
        )

    checks["poisson_solver"] = base.mb.has_block(
        text, f"Variables/{POISSON_VARIABLE}"
    )
    checks["poisson_not_aux"] = not base.mb.has_block(
        text, f"AuxVariables/{POISSON_VARIABLE}"
    )

    for name in FROZEN_ELECTRON_VARIABLES:
        checks[f"electron_frozen_aux:{name}"] = base.mb.has_block(
            text, f"AuxVariables/{name}"
        )
        checks[f"electron_not_solver:{name}"] = not base.mb.has_block(
            text, f"Variables/{name}"
        )

    kernel_vars = _owned_variables(text, "FVKernels")
    bc_vars = _owned_variables(text, "FVBCs")
    aux_kernel_vars = _owned_variables(text, "AuxKernels")

    checks["solver_owners_heavy_or_poisson"] = bool(kernel_vars) and all(
        variable in SOLVER_VARIABLES for variable in kernel_vars
    )
    checks["bc_owners_heavy_or_poisson"] = all(
        variable in SOLVER_VARIABLES for variable in bc_vars
    )
    checks["no_electron_time_kernel"] = not base.mb.has_block(
        text, "FVKernels/n_e_time"
    )
    checks["no_electron_energy_time_kernel"] = not base.mb.has_block(
        text, "FVKernels/s5r_n_epsilon_time"
    )
    checks["poisson_diffusion_present"] = base.mb.has_block(
        text, "FVKernels/r31_phi_diffusion"
    )
    checks["poisson_charge_source_present"] = base.mb.has_block(
        text, "FVKernels/r31_phi_charge_source"
    )
    checks["frozen_electrons_not_written_by_auxkernel"] = all(
        variable not in FROZEN_ELECTRON_VARIABLES for variable in aux_kernel_vars
    )

    checks["no_multiapps"] = not base.mb.has_block(text, "MultiApps")
    checks["no_transfers"] = not base.mb.has_block(text, "Transfers")
    checks["five_step_dt"] = math.isclose(
        float(base.mp.get_parameter(text, "Executioner", "dt") or "nan"),
        HEAVY_DT_S,
        rel_tol=0.0,
        abs_tol=1.0e-20,
    )
    checks["ten_ns_end"] = math.isclose(
        float(base.mp.get_parameter(text, "Executioner", "end_time") or "nan"),
        TOTAL_TIME_S,
        rel_tol=0.0,
        abs_tol=1.0e-20,
    )
    checks["exodus_enabled"] = (
        (
            base.mp.unquote(
                base.mp.get_parameter(text, "Outputs", "exodus")
            )
            or ""
        ).lower()
        == "true"
    )
    checks["outputs_each_step"] = (
        "TIMESTEP_END"
        in base.mp.words(base.mp.get_parameter(text, "Outputs", "execute_on"))
    )

    liveness = _root_liveness(text)
    missing_pp_refs = _missing_postprocessor_references(text)
    checks["no_dead_root_parameters"] = not liveness["dead_root_parameters"]
    checks["all_pp_dependencies_present"] = not missing_pp_refs

    failed = sorted(key for key, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "kernel_variables": kernel_vars,
        "bc_variables": bc_vars,
        "aux_kernel_variables": aux_kernel_vars,
        "root_liveness": liveness,
        "missing_postprocessor_references": missing_pp_refs,
    }


def _build_case() -> tuple[str, dict[str, Any]]:
    production_text, production_meta = base.w5._build_case(
        dt_s=base.w5.BASELINE_DT_S, uniform_refine=0
    )
    text = _build_heavy_poisson_input(production_text)
    audit = _audit_input(text)
    meta = {
        "issue": 236,
        "parent_issue": 234,
        "claim": "frozen_electrons_heavy_plus_poisson_five_step_discriminator",
        "operator_split": "none; single nonlinear heavy + Poisson application",
        "electron_model": (
            "n_e and n_epsilon frozen at production initial conditions; "
            "electron particle and energy equations removed"
        ),
        "total_time_s": TOTAL_TIME_S,
        "heavy_steps": HEAVY_STEPS,
        "dt_s": HEAVY_DT_S,
        "production_reference": production_meta,
        "audit": audit,
    }
    if audit["status"] != "PASS":
        raise base.Issue236Error(meta)
    return text, meta


def _self_test() -> dict[str, Any]:
    try:
        text, meta = _build_case()
        checks = {
            "case_builds": True,
            "audit": meta["audit"]["status"] == "PASS",
            "five_heavy_steps": meta["heavy_steps"] == HEAVY_STEPS,
            "no_multiapp": not base.mb.has_block(text, "MultiApps"),
            "hit_parse": bool(base.MooseInput(text).blocks),
        }

        synthetic = (
            "A = 1\n"
            "B = ${fparse A + 1}\n"
            "C = 3\n"
            "[Test]\n"
            "  value = ${C}\n"
            "[]\n"
        )
        pruned, report = _prune_dead_root_parameters(synthetic)
        checks["root_dependency_closure"] = (
            report["removed"] == ["A", "B"]
            and _root_liveness(pruned)["dead_root_parameters"] == []
            and "C = 3" in pruned
        )
        failed = sorted(key for key, ok in checks.items() if not ok)
        return {
            "status": "PASS" if not failed else "FAIL",
            "checks": checks,
            "failed_checks": failed,
        }
    except base.Issue236Error as error:
        detail = error.args[0] if error.args else str(error)
        return {
            "status": "FAIL",
            "checks": {"case_builds": False},
            "failed_checks": ["case_builds"],
            "detail": {"case_error": detail},
        }


def _stage(
    out: Path, *, dt_e: float
) -> tuple[Path, dict[str, Any]]:
    del dt_e  # retained only because base.run() supplies the legacy argument
    text, meta = _build_case()
    case_dir = out / "case"
    staged = base.stage_case(
        base.SOURCE,
        case_dir,
        input_text=text,
        input_name="input.i",
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=(
            "input_out*",
            "electron_sub*",
            "*.log",
            "*.e",
            "*.exo",
            "prepare_evidence.json",
        ),
    )
    base.w5.s5r._copy_runtime_assets(case_dir)

    meta["staging"] = staged
    meta["references"] = base.validate_referenced_files(
        text, case_dir, skip_dynamic=True
    )
    (case_dir / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return case_dir, meta


def _unique_rows_by_time(
    rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    by_time: dict[float, dict[str, str]] = {}
    for row in rows:
        time = float(row["time"])
        if time > 0.0:
            by_time[time] = row
    return [by_time[t] for t in sorted(by_time)]


def _runtime_analysis(
    case_dir: Path, *, dt_e: float, returncode: int, timed_out: bool
) -> dict[str, Any]:
    del dt_e
    csv_path = case_dir / "input_out.csv"
    exodus_path = case_dir / "input_out.e"
    result: dict[str, Any] = {
        "returncode": returncode,
        "timed_out": timed_out,
        "csv": str(csv_path) if csv_path.is_file() else None,
        "exodus": str(exodus_path) if exodus_path.is_file() else None,
        "expected_steps": HEAVY_STEPS,
    }
    gates = {
        "runtime_returncode_zero": returncode == 0,
        "not_timed_out": not timed_out,
        "csv_present": csv_path.is_file(),
        "exodus_present": exodus_path.is_file(),
    }
    if not csv_path.is_file():
        result["gates"] = gates
        result["hard_pass"] = all(gates.values())
        return result

    rows = base._read_csv(csv_path)
    physical = _unique_rows_by_time(rows)
    actual_times = [float(row["time"]) for row in physical]
    expected_times = [HEAVY_DT_S * i for i in range(1, HEAVY_STEPS + 1)]
    times_match = len(actual_times) == len(expected_times) and all(
        math.isclose(a, e, rel_tol=0.0, abs_tol=1.0e-18)
        for a, e in zip(actual_times, expected_times)
    )
    gates.update(
        {
            "five_steps": len(physical) == HEAVY_STEPS,
            "step_times": times_match,
            "final_time": bool(actual_times)
            and math.isclose(
                actual_times[-1],
                TOTAL_TIME_S,
                rel_tol=0.0,
                abs_tol=1.0e-18,
            ),
        }
    )

    result.update(
        {
            "physical_rows": len(physical),
            "times_s": actual_times,
            "gates": gates,
            "hard_pass": all(gates.values()),
        }
    )
    return result


base._stage = _stage
base._runtime_analysis = _runtime_analysis
base.self_test = _self_test

if __name__ == "__main__":
    raise SystemExit(base.main())
