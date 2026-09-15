#!/usr/bin/env python3
"""CI entrypoint for Issue-236 M1-A with governed W5 runtime-asset staging.

Kept separate from the scientific split builder so harness/runtime corrections
remain visible: it stages the W5 rate/chemistry assets, strips inherited
heavy-system diagnostics from the fast electron child, and trims production
root parameters that have no owner in the no-solve parent state carrier.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run as base


_base_build_parent_input = base.build_parent_input
_base_prune_child_flow_ownership = base._prune_child_flow_ownership
_base_audit_child = base._audit_child
_base_self_test = base.self_test

PARENT_UNUSED_ROOT_PARAMETERS = (
    "T_g_value",
    "T_e_value",
    "n_e_value",
    "mu_const",
    "e_over_kB_K_per_V",
    "inlet_mdot_value",
    "inlet_mdot_O2s_value",
    "inlet_mdot_O2p_value",
    "inlet_mdot_O_value",
    "inlet_mdot_Om_value",
    "inlet_mdot_Op_value",
    "inlet_mdot_Os_value",
)


def _remove_root_assignment(text: str, name: str) -> str:
    """Remove one unindented HIT root assignment and reject ambiguity."""
    pattern = re.compile(
        rf"(?m)^{re.escape(name)}\s*=\s*[^#\r\n]*\s*(?:#.*)?(?:\r?\n|$)"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise base.Issue236Error(
            f"expected one root assignment for {name}, found {len(matches)}"
        )
    match = matches[0]
    return text[: match.start()] + text[match.end() :]


def _build_parent_input(production_text: str) -> str:
    """Build the no-solve parent and remove scalars with no remaining owner."""
    text = _base_build_parent_input(production_text)
    for name in PARENT_UNUSED_ROOT_PARAMETERS:
        text = _remove_root_assignment(text, name)
    return text


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


def _audit_child(text: str, *, dt_e: float) -> dict[str, Any]:
    """Extend the split audit with exact fast-only diagnostic ownership."""
    result = _base_audit_child(text, dt_e=dt_e)
    remaining = _rc_dependent_postprocessors(text)
    postprocessor_names = {
        base._name(path) for path in base._children(text, "Postprocessors")
    }
    expected_postprocessors = set(base.CHILD_FAST_PPS)
    result["checks"]["no_rc_dependent_postprocessors"] = not remaining
    result["checks"]["child_postprocessors_fast_only"] = (
        postprocessor_names == expected_postprocessors
    )
    result["rc_dependent_postprocessors"] = remaining
    result["postprocessors"] = sorted(postprocessor_names)
    result["failed_checks"] = sorted(key for key, ok in result["checks"].items() if not ok)
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
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
    """Contain split-construction failures as structured governed evidence."""
    try:
        return _base_self_test()
    except base.Issue236Error as error:
        detail = error.args[0] if error.args else str(error)
        return {
            "status": "FAIL",
            "checks": {"split_builds": False},
            "failed_checks": ["split_builds"],
            "detail": {"split_error": detail},
        }


base.build_parent_input = _build_parent_input
base._prune_child_flow_ownership = _prune_child_flow_ownership
base._audit_child = _audit_child
base._stage = _stage
base.self_test = _self_test

if __name__ == "__main__":
    raise SystemExit(base.main())
