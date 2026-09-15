#!/usr/bin/env python3
"""Live-electron Issue-236 CI discriminator.

Schedule:
* heavy/ion parent: dt_h = 1e-8 s, 10 steps, t_end = 1e-7 s;
* electron density + electron energy + Poisson child: dt_e = 1e-9 s;
* 10 electron subcycles follow each heavy step (100 electron steps total);
* electron particle and energy surface losses remain active.

For this discriminator the strict grounded-sheath W3/W4.5 primary-electron
owners are replaced in the child by the previously validated COMSOL-style
thermal particle/energy wall-loss closures.  This keeps surface loss active
even if the plasma-side potential crosses below ground, without freezing the
electron state.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run as base
from experiments.Issue217_sheath_energy_closure import run as w45
from experiments.Issue27_surface_reactions.controlled_wall import electron_wall as a7
from experiments.historical_recipe_support import issue26_energy_chain as energy


TOTAL_TIME_S = 1.0e-7
HEAVY_STEPS = 10
HEAVY_DT_S = 1.0e-8
ELECTRON_DT_S = 1.0e-9
ELECTRON_STEPS_PER_HEAVY = 10

if not math.isclose(HEAVY_STEPS * HEAVY_DT_S, TOTAL_TIME_S, rel_tol=0.0, abs_tol=1e-22):
    raise RuntimeError("inconsistent heavy schedule")

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

PARTICLE_MATERIAL = "issue236_live_electron_surface_particle_material"
PARTICLE_FUNCTOR = "issue236_live_electron_surface_particle_flux"
ENERGY_MATERIAL = "issue236_live_electron_surface_energy_material"
ENERGY_FUNCTOR = "issue236_live_electron_surface_energy_flux"


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
    }


def _prune_dead_root_parameters(text: str) -> str:
    while True:
        report = _root_liveness(text)
        dead = set(report["dead_root_parameters"])
        if not dead:
            return text
        roots = _root_assignment_table(text)
        dead_lines = {int(roots[name]["line_index"]) for name in dead}
        lines = text.splitlines(keepends=True)
        text = "".join(line for index, line in enumerate(lines) if index not in dead_lines)


def _missing_postprocessor_references(text: str) -> list[str]:
    targets: set[str] = set()
    for line in text.splitlines():
        match = _PP_REF_RE.match(_strip_hit_comment(line))
        if match:
            targets.add(match.group(2))
    return sorted(
        target
        for target in targets
        if not base.mb.has_block(text, f"Postprocessors/{target}")
    )


def _fast_bc_names(production_text: str) -> set[str]:
    result: set[str] = set()
    for path in base._children(production_text, "FVBCs"):
        variable = base.mp.unquote(base.mp.get_parameter(production_text, path, "variable"))
        if variable in base.FAST_SOLVER_VARIABLES:
            result.add(base._name(path))
    return result


def _set_parent_output_policy(text: str) -> str:
    for name in base.PARENT_FAST_PPS:
        text = base.mp.upsert_parameter(
            text, f"Postprocessors/{name}", "execute_on", "'INITIAL FINAL'"
        )
    if base.mb.has_block(text, "Outputs"):
        text = base.mp.upsert_parameter(
            text, "Outputs", "execute_on", "'INITIAL TIMESTEP_END FINAL'"
        )
        text = base.mp.upsert_parameter(text, "Outputs", "exodus", "true")
    return text


def _build_parent_input(production_text: str) -> str:
    removed_fast_bcs = _fast_bc_names(production_text)

    # Preserve heavy-side postprocessors required by inlet/flow dependencies.
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
    text = base.mp.upsert_parameter(text, "Executioner", "dt", f"{HEAVY_DT_S:.17g}")
    text = base.mp.upsert_parameter(text, "Executioner", "end_time", f"{TOTAL_TIME_S:.17g}")

    # Heavy advances first; the fast child then catches up to the new sync time.
    text = base.mp.upsert_parameter(
        text, "MultiApps/electron", "execute_on", "TIMESTEP_END"
    )
    text = _set_parent_output_policy(text)
    return _prune_dead_root_parameters(text)


def _replace_strict_sheath_with_thermal_surface_loss(text: str) -> str:
    particle_path = f"FVBCs/{w45.PARTICLE_BC}"
    energy_path = f"FVBCs/{w45.ENERGY_BC}"
    if not base.mb.has_block(text, particle_path):
        raise base.Issue236Error(f"missing electron particle surface owner: {particle_path}")
    if not base.mb.has_block(text, energy_path):
        raise base.Issue236Error(f"missing electron energy surface owner: {energy_path}")

    for path in (
        f"FunctorMaterials/{PARTICLE_MATERIAL}",
        f"FunctorMaterials/{ENERGY_MATERIAL}",
    ):
        if base.mb.has_block(text, path):
            raise base.Issue236Error(f"duplicate live-electron wall material: {path}")

    text = base.mb.remove_block(text, particle_path)
    text = base.mb.remove_block(text, energy_path)

    walls = "'" + " ".join(w45.WALLS) + "'"
    particle_expression = (
        f"0.5*ne_hat*sqrt(16.0*{a7.ELEMENTARY_CHARGE_C:.17g}*mean_ev/"
        f"(3.0*3.14159265358979323846*{a7.ELECTRON_MASS_KG:.17g}))"
    )
    energy_expression = (
        f"{5.0/6.0:.17g}*eps_hat*sqrt(16.0*{a7.ELEMENTARY_CHARGE_C:.17g}*mean_ev/"
        f"(3.0*3.14159265358979323846*{a7.ELECTRON_MASS_KG:.17g}))"
    )

    text = base.mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{PARTICLE_MATERIAL}]
    type = ADParsedFunctorMaterial
    property_name = {PARTICLE_FUNCTOR}
    functor_names = 'n_e mean_en_solved'
    functor_symbols = 'ne_hat mean_ev'
    expression = '{particle_expression}'
    block = plasma
  []""",
    )
    text = base.mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{ENERGY_MATERIAL}]
    type = ADParsedFunctorMaterial
    property_name = {ENERGY_FUNCTOR}
    functor_names = 'n_epsilon mean_en_solved'
    functor_symbols = 'eps_hat mean_ev'
    expression = '{energy_expression}'
    block = plasma
  []""",
    )
    text = base.mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{w45.PARTICLE_BC}]
    type = FVFunctorNeumannBC
    variable = n_e
    boundary = {walls}
    functor = {PARTICLE_FUNCTOR}
    factor = -1
  []""",
    )
    text = base.mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{w45.ENERGY_BC}]
    type = FVFunctorNeumannBC
    variable = n_epsilon
    boundary = {walls}
    functor = {ENERGY_FUNCTOR}
    factor = -1
  []""",
    )
    return text


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    text = _base_build_child_input(production_text, dt_e=dt_e)
    text = _replace_strict_sheath_with_thermal_surface_loss(text)
    text = base.mp.upsert_parameter(text, "Executioner", "end_time", f"{TOTAL_TIME_S:.17g}")
    if base.mb.has_block(text, "Outputs"):
        text = base.mp.upsert_parameter(text, "Outputs", "file_base", "electron_sub")
        text = base.mp.upsert_parameter(text, "Outputs", "exodus", "true")
        text = base.mp.upsert_parameter(
            text, "Outputs", "execute_on", "'INITIAL TIMESTEP_END'"
        )
    return _prune_dead_root_parameters(text)


def _prune_child_flow_ownership(text: str) -> str:
    text = _base_prune_child_flow_ownership(text)
    # Production diagnostics can retain heavy/flow-only dependencies after the split.
    # Rebuild only the child synchronization observables in base.build_child_input().
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
    result["checks"]["parent_dt"] = math.isclose(
        float(base.mp.get_parameter(text, "Executioner", "dt") or "nan"),
        HEAVY_DT_S,
        rel_tol=0.0,
        abs_tol=1e-20,
    )
    result["checks"]["parent_end_time"] = math.isclose(
        float(base.mp.get_parameter(text, "Executioner", "end_time") or "nan"),
        TOTAL_TIME_S,
        rel_tol=0.0,
        abs_tol=1e-20,
    )
    result["checks"].pop("multiapp_at_timestep_begin", None)
    result["checks"]["multiapp_at_timestep_end"] = (
        base.mp.unquote(base.mp.get_parameter(text, "MultiApps/electron", "execute_on"))
        == "TIMESTEP_END"
    )
    result["checks"]["parent_exodus_enabled"] = (
        (base.mp.unquote(base.mp.get_parameter(text, "Outputs", "exodus")) or "").lower()
        == "true"
    )
    result["checks"]["all_parent_pp_dependencies_present"] = (
        not _missing_postprocessor_references(text)
    )
    result["checks"]["no_dead_root_parameters"] = not _root_liveness(text)[
        "dead_root_parameters"
    ]
    return _finalize_audit(result)


def _audit_child(text: str, *, dt_e: float) -> dict[str, Any]:
    result = _base_audit_child(text, dt_e=dt_e)
    result["checks"]["child_end_time"] = math.isclose(
        float(base.mp.get_parameter(text, "Executioner", "end_time") or "nan"),
        TOTAL_TIME_S,
        rel_tol=0.0,
        abs_tol=1e-20,
    )
    result["checks"]["child_exodus_enabled"] = (
        (base.mp.unquote(base.mp.get_parameter(text, "Outputs", "exodus")) or "").lower()
        == "true"
    )

    particle_path = f"FVBCs/{w45.PARTICLE_BC}"
    energy_path = f"FVBCs/{w45.ENERGY_BC}"
    expected_walls = set(w45.WALLS)
    result["checks"]["electron_particle_surface_loss_active"] = (
        base.mb.has_block(text, particle_path)
        and base.mp.get_parameter(text, particle_path, "type") == "FVFunctorNeumannBC"
        and set(base.mp.words(base.mp.get_parameter(text, particle_path, "boundary")))
        == expected_walls
        and math.isclose(
            float(base.mp.get_parameter(text, particle_path, "factor") or "nan"),
            -1.0,
            rel_tol=0.0,
            abs_tol=0.0,
        )
    )
    result["checks"]["electron_energy_surface_loss_active"] = (
        base.mb.has_block(text, energy_path)
        and base.mp.get_parameter(text, energy_path, "type") == "FVFunctorNeumannBC"
        and set(base.mp.words(base.mp.get_parameter(text, energy_path, "boundary")))
        == expected_walls
        and math.isclose(
            float(base.mp.get_parameter(text, energy_path, "factor") or "nan"),
            -1.0,
            rel_tol=0.0,
            abs_tol=0.0,
        )
    )
    result["checks"]["surface_loss_materials_present"] = (
        base.mb.has_block(text, f"FunctorMaterials/{PARTICLE_MATERIAL}")
        and base.mb.has_block(text, f"FunctorMaterials/{ENERGY_MATERIAL}")
    )
    result["checks"]["no_dead_root_parameters"] = not _root_liveness(text)[
        "dead_root_parameters"
    ]
    return _finalize_audit(result)


def _build_split(*, dt_e: float = ELECTRON_DT_S) -> tuple[str, str, dict[str, Any]]:
    if not math.isfinite(dt_e) or dt_e <= 0.0:
        raise base.Issue236Error(f"invalid electron timestep {dt_e}")
    ratio = HEAVY_DT_S / dt_e
    if not math.isclose(ratio, round(ratio), rel_tol=0.0, abs_tol=1e-9):
        raise base.Issue236Error(
            f"heavy/electron timestep ratio must be integer, got {ratio}"
        )

    production_text, production_meta = base.w5._build_case(
        dt_s=base.w5.BASELINE_DT_S, uniform_refine=0
    )
    parent = base.build_parent_input(production_text)
    child = base.build_child_input(production_text, dt_e=dt_e)
    parent_audit = base._audit_parent(parent)
    child_audit = base._audit_child(child, dt_e=dt_e)

    subcycles_per_heavy = int(round(HEAVY_DT_S / dt_e))
    total_subcycles = int(round(TOTAL_TIME_S / dt_e))
    meta = {
        "issue": 236,
        "parent_issue": 234,
        "claim": "live_electrons_with_surface_loss_10_heavy_steps",
        "operator_split": (
            "heavy solve -> TIMESTEP_END heavy transfer -> electron/energy/Poisson "
            "subcycles -> fast transfer back"
        ),
        "electron_model": "solved n_e + solved n_epsilon + Poisson; not frozen",
        "electron_surface_loss": (
            "COMSOL-style thermal particle and energy wall losses; ion-induced SEE retained"
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
        p for p in case_dir.rglob("*.e") if "electron_sub" in p.name and p.is_file()
    )
    return max(candidates, key=lambda p: p.stat().st_size) if candidates else None


def _unique_rows_by_time(rows: list[dict[str, str]]) -> list[dict[str, str]]:
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
    if not parent_csv.is_file() or child_csv is None:
        result["gates"] = gates
        result["hard_pass"] = all(gates.values())
        return result

    parent_rows = _unique_rows_by_time(base._read_csv(parent_csv))
    child_rows = _unique_rows_by_time(base._read_csv(child_csv))
    parent_final = parent_rows[-1] if parent_rows else {}
    child_final = child_rows[-1] if child_rows else {}

    expected_parent_times = [HEAVY_DT_S * i for i in range(1, HEAVY_STEPS + 1)]
    actual_parent_times = [float(row["time"]) for row in parent_rows]
    child_times = [float(row["time"]) for row in child_rows]

    gates.update(
        {
            "parent_step_count": len(parent_rows) == HEAVY_STEPS,
            "parent_step_times": len(actual_parent_times) == HEAVY_STEPS
            and all(
                math.isclose(a, e, rel_tol=0.0, abs_tol=1e-14)
                for a, e in zip(actual_parent_times, expected_parent_times)
            ),
            "child_subcycle_count": len(child_rows) == expected_total_subcycles,
            "subcycles_per_heavy": expected_per_heavy == ELECTRON_STEPS_PER_HEAVY,
            "child_hits_every_heavy_sync": all(
                any(math.isclose(t, sync, rel_tol=0.0, abs_tol=1e-14) for t in child_times)
                for sync in expected_parent_times
            ),
            "parent_final_time": bool(parent_final)
            and math.isclose(float(parent_final["time"]), TOTAL_TIME_S, rel_tol=0.0, abs_tol=1e-14),
            "child_final_time": bool(child_final)
            and math.isclose(float(child_final["time"]), TOTAL_TIME_S, rel_tol=0.0, abs_tol=1e-14),
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
        scale = max(abs(pv), abs(cv), 1e-300)
        rel = abs(pv - cv) / scale
        mirror[parent_key] = {
            "parent": pv,
            "child": cv,
            "relative_difference": rel,
        }
        gates[f"mirror:{parent_key}"] = rel <= 1e-10

    result.update(
        {
            "parent_physical_rows": len(parent_rows),
            "child_physical_rows": len(child_rows),
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
        result["checks"]["ten_heavy_steps"] = meta["heavy_steps"] == 10
        result["checks"]["heavy_dt_1e_8"] = math.isclose(
            meta["dt_h_s"], 1e-8, rel_tol=0.0, abs_tol=0.0
        )
        result["checks"]["electron_dt_1e_9"] = math.isclose(
            meta["dt_e_s"], 1e-9, rel_tol=0.0, abs_tol=0.0
        )
        result["checks"]["ten_electron_steps_per_heavy"] = (
            meta["subcycles_per_heavy"] == 10
        )
        result["checks"]["hundred_total_electron_steps"] = (
            meta["subcycles_expected"] == 100
        )
        result["checks"]["electrons_are_solver_variables"] = all(
            base.mb.has_block(child, f"Variables/{name}") for name in ("n_e", "n_epsilon")
        )
        result["checks"]["particle_surface_loss_present"] = base.mb.has_block(
            child, f"FVBCs/{w45.PARTICLE_BC}"
        )
        result["checks"]["energy_surface_loss_present"] = base.mb.has_block(
            child, f"FVBCs/{w45.ENERGY_BC}"
        )
        result["checks"]["heavy_first_execute_point"] = (
            base.mp.unquote(
                base.mp.get_parameter(parent, "MultiApps/electron", "execute_on")
            )
            == "TIMESTEP_END"
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
