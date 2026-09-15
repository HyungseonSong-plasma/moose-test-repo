#!/usr/bin/env python3
"""CI entrypoint for Issue-236 M1-A with governed W5 runtime-asset staging.

Kept separate from the scientific split builder so harness/runtime corrections
remain visible: it stages the W5 rate/chemistry assets, strips inherited
heavy-system diagnostics from the fast electron child, and garbage-collects
root HIT parameters that no surviving object references after the split.
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

_ROOT_ASSIGNMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _strip_hit_comment(line: str) -> str:
    """Strip a HIT comment while preserving # characters inside quotes."""
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
    """Return unique unindented root assignments and their dependency payload."""
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
    """Compute live/dead root assignments from surviving HIT references."""
    roots = _root_assignment_table(text)
    names = set(roots)
    dependencies: dict[str, set[str]] = {name: set() for name in names}
    for name, entry in roots.items():
        rhs = str(entry["rhs"])
        dependencies[name] = {
            other
            for other in names
            if other != name and _mentions_symbol(rhs, other)
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
    """Remove the full transitive closure of unreferenced root assignments."""
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


def _build_parent_input(production_text: str) -> str:
    """Build the no-solve parent and garbage-collect dead production scalars."""
    text = _base_build_parent_input(production_text)
    return _prune_dead_root_parameters(text)[0]


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    """Build the fast child and garbage-collect roots orphaned by heavy pruning."""
    text = _base_build_child_input(production_text, dt_e=dt_e)
    return _prune_dead_root_parameters(text)[0]


def _rc_dependent_postprocessors(text: str) -> list[str]:
    """Return child postprocessors that still require the removed rc object."""
    return [
        path
        for path in base._children(text, "Postprocessors")
        if base.mp.unquote(base.mp.get_parameter(text, path, "rhie_chow_user_object")) == "rc"
    ]


def _prune_child_flow_ownership(text: str) -> str:
    """Remove inherited heavy-flow ownership and all production diagnostics."""
    text = _base_prune_child_flow_ownership(text)
    # Production postprocessors depend on heavy-flow/user-object/functor owners
    # intentionally absent from the fast child. build_child_input() recreates
    # only the three M1-A fast-state postprocessors after this pruning step.
    if base.mb.has_block(text, "Postprocessors"):
        text = base.mb.remove_block(text, "Postprocessors")
    return text


def _finalize_audit(result: dict[str, Any]) -> dict[str, Any]:
    result["failed_checks"] = sorted(key for key, ok in result["checks"].items() if not ok)
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


def _audit_parent(text: str) -> dict[str, Any]:
    """Extend the parent audit with root-parameter liveness."""
    result = _base_audit_parent(text)
    liveness = _root_liveness(text)
    result["checks"]["no_dead_root_parameters"] = not liveness["dead_root_parameters"]
    result["root_liveness"] = liveness
    return _finalize_audit(result)


def _audit_child(text: str, *, dt_e: float) -> dict[str, Any]:
    """Extend the child audit with fast-only diagnostics and root liveness."""
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

    # Exact staging contract already used by Issue-216 W5 and its R2 successors.
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
    """Contain split failures and verify transitive root-liveness pruning."""
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
