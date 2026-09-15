#!/usr/bin/env python3
"""CI entrypoint for Issue-236 M1-A with governed staging and split audits.

The parent is the solving heavy-fluid/heavy-species application.  The child
owns only electron density, electron energy, and Poisson.  This discriminator
uses a staggered heavy-first schedule over 10 ns:

* five heavy steps with dt_h = 2 ns;
* after each heavy solve, parent heavy state is transferred at TIMESTEP_END;
* electron/energy/Poisson then sub-cycles 20 times with dt_e = 0.1 ns;
* fast child state is transferred back before the next heavy step.

Both parent and child Exodus output are retained for spatial inspection.
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
ELECTRON_STEPS_PER_HEAVY = 20
ELECTRON_DT_S = HEAVY_DT_S / ELECTRON_STEPS_PER_HEAVY

# The base builder uses DT_H_S as the parent synchronization interval.  For
# this CI discriminator the interval is one heavy step, while end_time remains
# TOTAL_TIME_S and is corrected by the wrappers below.
base.DT_H_S = HEAVY_DT_S
base.DT_E_SMOKE_S = ELECTRON_DT_S

_base_build_parent_input = base.build_parent_input
_base_build_child_input = base.build_child_input
_base_prune_child_flow_ownership = base._prune_child_flow_ownership
_base_audit_parent = base._audit_parent
_base_audit_child = base._audit_child
_base_self_test = base.self_test
_base_remove_top_if_present = base._remove_top_if_present

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
    return re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text
    ) is not None


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


def _fast_bc_names(production_text: str) -> set[str]:
    removed: set[str] = set()
    for path in base._children(production_text, "FVBCs"):
        variable = base.mp.unquote(base.mp.get_parameter(production_text, path, "variable"))
        if variable in base.FAST_SOLVER_VARIABLES:
            removed.add(base._name(path))
    return removed


def _set_parent_output_policy(text: str) -> str:
    """Keep final mirror observation while emitting every heavy state to Exodus."""
    for name in base.PARENT_FAST_PPS:
        text = base.mp.upsert_parameter(
            text,
            f"Postprocessors/{name}",
            "execute_on",
            "'INITIAL FINAL'",
        )
    if base.mb.has_block(text, "Outputs"):
        text = base.mp.upsert_parameter(
            text, "Outputs", "execute_on", "'INITIAL TIMESTEP_END FINAL'"
        )
        text = base.mp.upsert_parameter(text, "Outputs", "exodus", "true")
    return text


def _build_parent_input(production_text: str) -> str:
    """Build five-step heavy parent and preserve its required PP dependencies."""
    removed_fast_bcs = _fast_bc_names(production_text)

    # The base split removes all parent Postprocessors.  A solving heavy parent
    # needs inlet Receiver/area postprocessors, so preserve them here.
    original_remove_top = base._remove_top_if_present

    def preserve_postprocessors(text: str, name: str) -> str:
        if name == "Postprocessors":
            return text
        return _base_remove_top_if_present(text, name)

    base._remove_top_if_present = preserve_postprocessors
    try:
        text = _base_build_parent_input(production_text)
    finally:
        base._remove_top_if_present = original_remove_top

    text = base._remove_postprocessors_for_missing_bcs(text, removed_fast_bcs)

    # Heavy advances first.  At TIMESTEP_END its new state is sent to the child,
    # the child catches up by sub-cycling, then fast state returns to the parent.
    text = base.mp.upsert_parameter(text, "Executioner", "dt", f"{HEAVY_DT_S:.17g}")
    text = base.mp.upsert_parameter(text, "Executioner", "end_time", f"{TOTAL_TIME_S:.17g}")
    text = base.mp.upsert_parameter(
        text, "MultiApps/electron", "execute_on", "TIMESTEP_END"
    )
    text = _set_parent_output_policy(text)
    return _prune_dead_root_parameters(text)[0]


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    """Build fast child that follows each heavy step to the shared sync time."""
    text = _base_build_child_input(production_text, dt_e=dt_e)
    text = base.mp.upsert_parameter(text, "Executioner", "end_time", f"{TOTAL_TIME_S:.17g}")
    if base.mb.has_block(text, "Outputs"):
        text = base.mp.upsert_parameter(text, "Outputs", "file_base", "electron_sub")
        text = base.mp.upsert_parameter(text, "Outputs", "exodus", "true")
        text = base.mp.upsert_parameter(
            text, "Outputs", "execute_on", "'INITIAL TIMESTEP_END'"
        )
    return _prune_dead_root_parameters(text)[0]


def _rc_dependent_postprocessors(text: str) -> list[str]:
    return [
        path
        for path in base._children(text, "Postprocessors")
        if base.mp.unquote(base.mp.get_parameter(text, path, "rhie_chow_user_object")) == "rc"
    ]


def _prune_child_flow_ownership(text: str) -> str:
    text = _base_prune_child_flow_ownership(text)
    if base.mb.has_block(text, "Postprocessors"):
        text = base.mb.remove_block(text, "Postprocessors")
    return text


def _finalize_audit(result: dict[str, Any]) -> dict[str, Any]:
    result["failed_checks"] = sorted(
        key for key, ok in result["checks"].items() if not ok
    )
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


def _audit_parent(text: str) -> dict[str, Any]:
    result = _base_audit_parent(text)
    # Base M1-A expected a one-step TIMESTEP_BEGIN split.  Replace those two
    # scheduling gates with the heavy-first five-step contract.
    result["checks"]["parent_dt"] = math.isclose(
        float(base.mp.get_parameter(text, "Executioner", "dt") or "nan"),
        HEAVY_DT_S,
        rel_tol=0.0,
        abs_tol=1.0e-20,
    )
    result["checks"]["parent_end_time"] = math.isclose(
        float(base.mp.get_parameter(text, "Executioner", "end_time") or "nan"),
        TOTAL_TIME_S,
        rel_tol=0.0,
        abs_tol=1.0e-20,
    )
    result["checks"].pop("multiapp_at_timestep_begin", None)
    result["checks"]["multiapp_at_timestep_end"] = (
        base.mp.unquote(base.mp.get_parameter(text, "MultiApps/electron", "execute_on"))
        == "TIMESTEP_END"
    )

    liveness = _root_liveness(text)
    pp_refs = _postprocessor_references(text)
    missing_pp_refs = _missing_postprocessor_references(text)
    parent_pp_execute_on = {
        name: base.mp.words(
            base.mp.get_parameter(text, f"Postprocessors/{name}", "execute_on")
        )
        for name in base.PARENT_FAST_PPS
    }
    output_execute_on = (
        base.mp.words(base.mp.get_parameter(text, "Outputs", "execute_on"))
        if base.mb.has_block(text, "Outputs")
        else []
    )

    result["checks"]["no_dead_root_parameters"] = not liveness["dead_root_parameters"]
    result["checks"]["all_parent_pp_dependencies_present"] = not missing_pp_refs
    result["checks"]["parent_mirrors_observed_at_final"] = all(
        "FINAL" in execute_on for execute_on in parent_pp_execute_on.values()
    )
    result["checks"]["parent_outputs_each_heavy_step"] = (
        "TIMESTEP_END" in output_execute_on
    )
    result["checks"]["parent_exodus_enabled"] = (
        (base.mp.unquote(base.mp.get_parameter(text, "Outputs", "exodus")) or "").lower()
        == "true"
    )
    result["root_liveness"] = liveness
    result["postprocessor_references"] = pp_refs
    result["missing_postprocessor_references"] = missing_pp_refs
    result["parent_postprocessor_execute_on"] = parent_pp_execute_on
    result["parent_output_execute_on"] = output_execute_on
    return _finalize_audit(result)


def _audit_child(text: str, *, dt_e: float) -> dict[str, Any]:
    result = _base_audit_child(text, dt_e=dt_e)
    result["checks"]["child_end_time"] = math.isclose(
        float(base.mp.get_parameter(text, "Executioner", "end_time") or "nan"),
        TOTAL_TIME_S,
        rel_tol=0.0,
        abs_tol=1.0e-20,
    )
    result["checks"]["child_exodus_enabled"] = (
        (base.mp.unquote(base.mp.get_parameter(text, "Outputs", "exodus")) or "").lower()
        == "true"
    )

    remaining = _rc_dependent_postprocessors(text)
    postprocessor_names = {
        base._name(path) for path in base._children(text, "Postprocessors")
    }
    expected_postprocessors = set(base.CHILD_FAST_PPS)
    liveness = _root_liveness(text)
    result["checks"]["no_rc_dependent_postprocessors"] = not remaining
    result["checks"]["child_postprocessors_fast_only"] = (
        postprocessor_names == expected_postprocessors
    )
    result["checks"]["no_dead_root_parameters"] = not liveness["dead_root_parameters"]
    result["rc_dependent_postprocessors"] = remaining
    result["postprocessors"] = sorted(postprocessor_names)
    result["root_liveness"] = liveness
    return _finalize_audit(result)


def _build_split(*, dt_e: float = ELECTRON_DT_S) -> tuple[str, str, dict[str, Any]]:
    if not math.isclose(
        HEAVY_DT_S / dt_e,
        round(HEAVY_DT_S / dt_e),
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        raise base.Issue236Error(
            f"heavy/electron timestep ratio must be integer, got {HEAVY_DT_S / dt_e}"
        )

    production_text, production_meta = base.w5._build_case(
        dt_s=base.w5.BASELINE_DT_S, uniform_refine=0
    )
    parent = base.build_parent_input(production_text)
    child = base.build_child_input(production_text, dt_e=dt_e)
    parent_audit = base._audit_parent(parent)
    child_audit = base._audit_child(child, dt_e=dt_e)

    total_subcycles = int(round(TOTAL_TIME_S / dt_e))
    subcycles_per_heavy = int(round(HEAVY_DT_S / dt_e))
    meta = {
        "issue": 236,
        "parent_issue": 234,
        "claim": "five_heavy_steps_followed_by_electron_poisson_relaxation",
        "operator_split": (
            "heavy parent solve -> TIMESTEP_END heavy transfer -> electron/energy/Poisson "
            "subcycles -> fast transfer back; repeat five times"
        ),
        "total_time_s": TOTAL_TIME_S,
        "heavy_steps": HEAVY_STEPS,
        "dt_h_s": HEAVY_DT_S,
        "dt_e_s": dt_e,
        "subcycles_per_heavy": subcycles_per_heavy,
        "subcycles_expected": total_subcycles,
        "production_reference": production_meta,
        "parent_audit": parent_audit,
        "child_audit": child_audit,
    }
    if parent_audit["status"] != "PASS" or child_audit["status"] != "PASS":
        raise base.Issue236Error(meta)
    return parent, child, meta


def _find_child_exodus(case_dir: Path) -> Path | None:
    candidates = sorted(
        p
        for p in case_dir.rglob("*.e")
        if "electron_sub" in p.name and p.is_file()
    )
    return max(candidates, key=lambda p: p.stat().st_size) if candidates else None


def _unique_rows_by_time(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep the last output row for each physical time (FINAL may duplicate t_end)."""
    by_time: dict[float, dict[str, str]] = {}
    for row in rows:
        time = float(row["time"])
        if time > 0.0:
            by_time[time] = row
    return [by_time[t] for t in sorted(by_time)]


def _runtime_analysis(
    case_dir: Path, *, dt_e: float, returncode: int, timed_out: bool
) -> dict[str, Any]:
    expected_total_subcycles = int(round(TOTAL_TIME_S / dt_e))
    expected_per_heavy = int(round(HEAVY_DT_S / dt_e))
    parent_csv = case_dir / "input_out.csv"
    child_csv = base._find_child_csv(case_dir)
    parent_exodus = case_dir / "input_out.e"
    child_exodus = _find_child_exodus(case_dir)

    result: dict[str, Any] = {
        "returncode": returncode,
        "timed_out": timed_out,
        "parent_csv": str(parent_csv) if parent_csv.is_file() else None,
        "child_csv": str(child_csv) if child_csv else None,
        "parent_exodus": str(parent_exodus) if parent_exodus.is_file() else None,
        "child_exodus": str(child_exodus) if child_exodus else None,
        "expected_parent_steps": HEAVY_STEPS,
        "expected_subcycles_per_heavy": expected_per_heavy,
        "expected_subcycles_total": expected_total_subcycles,
    }
    gates = {
        "runtime_returncode_zero": returncode == 0,
        "not_timed_out": not timed_out,
        "parent_csv_present": parent_csv.is_file(),
        "child_csv_present": child_csv is not None,
        "parent_exodus_present": parent_exodus.is_file(),
        "child_exodus_present": child_exodus is not None,
    }
    if not all((parent_csv.is_file(), child_csv is not None)):
        result["gates"] = gates
        result["hard_pass"] = all(gates.values())
        return result

    parent_rows = base._read_csv(parent_csv)
    child_rows = base._read_csv(child_csv)
    parent_physical = _unique_rows_by_time(parent_rows)
    child_physical = _unique_rows_by_time(child_rows)
    parent_final = parent_physical[-1] if parent_physical else {}
    child_final = child_physical[-1] if child_physical else {}

    expected_parent_times = [HEAVY_DT_S * i for i in range(1, HEAVY_STEPS + 1)]
    actual_parent_times = [float(row["time"]) for row in parent_physical]
    parent_times_match = len(actual_parent_times) == len(expected_parent_times) and all(
        math.isclose(a, e, rel_tol=0.0, abs_tol=1.0e-18)
        for a, e in zip(actual_parent_times, expected_parent_times)
    )

    child_times = [float(row["time"]) for row in child_physical]
    child_hits_every_heavy_sync = all(
        any(math.isclose(t, sync, rel_tol=0.0, abs_tol=1.0e-18) for t in child_times)
        for sync in expected_parent_times
    )

    gates.update(
        {
            "five_parent_steps": len(parent_physical) == HEAVY_STEPS,
            "parent_step_times": parent_times_match,
            "child_subcycle_count": len(child_physical) == expected_total_subcycles,
            "twenty_subcycles_per_heavy": expected_per_heavy == ELECTRON_STEPS_PER_HEAVY,
            "child_hits_every_heavy_sync": child_hits_every_heavy_sync,
            "parent_sync_time": bool(parent_final)
            and math.isclose(
                float(parent_final["time"]), TOTAL_TIME_S, rel_tol=0.0, abs_tol=1.0e-18
            ),
            "child_sync_time": bool(child_final)
            and math.isclose(
                float(child_final["time"]), TOTAL_TIME_S, rel_tol=0.0, abs_tol=1.0e-18
            ),
        }
    )

    mirror_pairs = (
        ("m1_parent_n_e_hat_avg", "m1_child_n_e_hat_avg"),
        ("m1_parent_n_epsilon_hat_avg", "m1_child_n_epsilon_hat_avg"),
        ("m1_parent_phi_avg", "m1_child_phi_avg"),
    )
    mirror: dict[str, Any] = {}
    for parent_key, child_key in mirror_pairs:
        if parent_key not in parent_final or child_key not in child_final:
            gates[f"mirror_column:{parent_key}"] = False
            continue
        pv = float(parent_final[parent_key])
        cv = float(child_final[child_key])
        scale = max(abs(pv), abs(cv), 1.0e-300)
        rel = abs(pv - cv) / scale
        mirror[parent_key] = {
            "parent": pv,
            "child": cv,
            "relative_difference": rel,
        }
        gates[f"mirror:{parent_key}"] = rel <= 1.0e-10

    result.update(
        {
            "parent_physical_rows": len(parent_physical),
            "child_physical_rows": len(child_physical),
            "parent_times_s": actual_parent_times,
            "parent_final_time_s": float(parent_final["time"]) if parent_final else None,
            "child_final_time_s": float(child_final["time"]) if child_final else None,
            "mirror": mirror,
            "gates": gates,
            "hard_pass": all(gates.values()),
        }
    )
    return result


def _stage(out: Path, *, dt_e: float) -> tuple[Path, dict[str, Any]]:
    parent, child, meta = base.build_split(dt_e=dt_e)
    case_dir = out / "case"
    staged = base.stage_case(
        base.SOURCE,
        case_dir,
        input_text=parent,
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
    (case_dir / "electron_sub.i").write_text(child, encoding="utf-8")
    base.w5.s5r._copy_runtime_assets(case_dir)

    meta["staging"] = staged
    meta["parent_references"] = base.validate_referenced_files(
        parent, case_dir, skip_dynamic=True
    )
    meta["child_references"] = base.validate_referenced_files(
        child, case_dir, skip_dynamic=True
    )
    (case_dir / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return case_dir, meta


def _self_test() -> dict[str, Any]:
    try:
        result = _base_self_test()
        parent, child, meta = base.build_split(dt_e=ELECTRON_DT_S)
        synthetic = "A = 1\nB = ${fparse A + 1}\nC = 3\n[Test]\n  value = ${C}\n[]\n"
        pruned, report = _prune_dead_root_parameters(synthetic)
        result["checks"]["root_dependency_closure"] = (
            report["removed"] == ["A", "B"]
            and _root_liveness(pruned)["dead_root_parameters"] == []
            and "A =" not in pruned
            and "B =" not in pruned
            and "C = 3" in pruned
        )
        result["checks"]["five_heavy_steps"] = meta["heavy_steps"] == HEAVY_STEPS
        result["checks"]["twenty_electron_steps_per_heavy"] = (
            meta["subcycles_per_heavy"] == ELECTRON_STEPS_PER_HEAVY
        )
        result["checks"]["hundred_total_electron_steps"] = (
            meta["subcycles_expected"] == HEAVY_STEPS * ELECTRON_STEPS_PER_HEAVY
        )
        result["checks"]["heavy_first_execute_point"] = (
            base.mp.unquote(base.mp.get_parameter(parent, "MultiApps/electron", "execute_on"))
            == "TIMESTEP_END"
        )
        result["checks"]["parent_exodus_enabled"] = (
            (base.mp.unquote(base.mp.get_parameter(parent, "Outputs", "exodus")) or "").lower()
            == "true"
        )
        result["checks"]["child_exodus_enabled"] = (
            (base.mp.unquote(base.mp.get_parameter(child, "Outputs", "exodus")) or "").lower()
            == "true"
        )
        result["failed_checks"] = sorted(
            key for key, ok in result["checks"].items() if not ok
        )
        result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
        return result
    except base.Issue236Error as error:
        detail = error.args[0] if error.args else str(error)
        return {
            "status": "FAIL",
            "checks": {"split_builds": False},
            "failed_checks": ["split_builds"],
            "detail": {"split_error": detail},
        }


base.build_parent_input = _build_parent_input
base.build_child_input = _build_child_input
base._prune_child_flow_ownership = _prune_child_flow_ownership
base._audit_parent = _audit_parent
base._audit_child = _audit_child
base.build_split = _build_split
base._runtime_analysis = _runtime_analysis
base._stage = _stage
base.self_test = _self_test

if __name__ == "__main__":
    raise SystemExit(base.main())
