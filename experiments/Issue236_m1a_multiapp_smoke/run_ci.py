#!/usr/bin/env python3
"""CI entrypoint for Issue-236 M1-A with governed staging and split audits.

The parent remains the solving heavy-fluid/heavy-species application.  The
child owns only electron density, electron energy, and Poisson and sub-cycles.
This wrapper keeps runtime assets and only the diagnostics/dependencies needed
by each side of that ownership split.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run as base


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
    """Collect input parameters whose names explicitly identify PP dependencies."""
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


def _set_parent_final_observation(text: str) -> str:
    for name in base.PARENT_FAST_PPS:
        text = base.mp.upsert_parameter(
            text,
            f"Postprocessors/{name}",
            "execute_on",
            "'INITIAL FINAL'",
        )
    if base.mb.has_block(text, "Outputs"):
        text = base.mp.upsert_parameter(text, "Outputs", "execute_on", "'INITIAL FINAL'")
    return text


def _build_parent_input(production_text: str) -> str:
    """Keep heavy PP dependencies while pruning diagnostics tied to removed fast BCs."""
    removed_fast_bcs = _fast_bc_names(production_text)

    # The base split removes all parent Postprocessors.  That is too aggressive
    # for a solving heavy parent because inlet FVBCs consume Receiver/area PPs.
    # Preserve only the Postprocessors top block during base construction; keep
    # the base behavior for VectorPostprocessors and every other top-level block.
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

    # Remove only diagnostics whose FVBC owners were intentionally removed with
    # the fast subsystem.  Heavy inlet/outlet PPs remain available to heavy BCs.
    text = base._remove_postprocessors_for_missing_bcs(text, removed_fast_bcs)
    text = _set_parent_final_observation(text)
    return _prune_dead_root_parameters(text)[0]


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    text = _base_build_child_input(production_text, dt_e=dt_e)
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
    result["checks"]["parent_output_at_final"] = "FINAL" in output_execute_on
    result["root_liveness"] = liveness
    result["postprocessor_references"] = pp_refs
    result["missing_postprocessor_references"] = missing_pp_refs
    result["parent_postprocessor_execute_on"] = parent_pp_execute_on
    result["parent_output_execute_on"] = output_execute_on
    return _finalize_audit(result)


def _audit_child(text: str, *, dt_e: float) -> dict[str, Any]:
    result = _base_audit_child(text, dt_e=dt_e)
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
        synthetic = "A = 1\nB = ${fparse A + 1}\nC = 3\n[Test]\n  value = ${C}\n[]\n"
        pruned, report = _prune_dead_root_parameters(synthetic)
        result["checks"]["root_dependency_closure"] = (
            report["removed"] == ["A", "B"]
            and _root_liveness(pruned)["dead_root_parameters"] == []
            and "A =" not in pruned
            and "B =" not in pruned
            and "C = 3" in pruned
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
base._stage = _stage
base.self_test = _self_test

if __name__ == "__main__":
    raise SystemExit(base.main())
