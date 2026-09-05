"""Framework-schema evidence analysis for electron-inventory closure."""
from __future__ import annotations

import json
from typing import Any

from qpx_harness.adapters.moose.electron_inventory.constants import (
    CONSTRAINT_TYPE,
    DRIFT_TYPE,
    REQUIRED_CONSTRAINT_SCHEMA_PARAMETERS,
    REQUIRED_FVFLUX_SCHEMA_PARAMETERS,
)
from qpx_harness.domains.plasma.electron_inventory import ElectronInventoryNullspaceError


def _extract_moose_json(text: str) -> Any:
    start_marker = "**START JSON DATA**"
    end_marker = "**END JSON DATA**"
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        raise ElectronInventoryNullspaceError("MOOSE JSON markers are missing")
    payload = text[start + len(start_marker) : end].strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ElectronInventoryNullspaceError(f"invalid MOOSE JSON payload: {exc}") from exc


def _schema_presence_analysis(
    text: str,
    *,
    returncode: int,
    object_type: str,
    required_parameters: tuple[str, ...],
    semantic_terms: tuple[str, ...] = (),
) -> dict[str, Any]:
    if returncode != 0:
        return {
            "status": "HOLD",
            "class": "FRAMEWORK_SCHEMA_QUERY_FAIL",
            "reason": f"qpx --json-search returned {returncode}",
        }
    try:
        payload = _extract_moose_json(text)
    except ElectronInventoryNullspaceError as exc:
        return {
            "status": "HOLD",
            "class": "FRAMEWORK_SCHEMA_EVIDENCE_INSUFFICIENT",
            "reason": str(exc),
        }

    serialized = json.dumps(payload, sort_keys=True)
    lower = serialized.lower()
    object_present = object_type in serialized
    parameter_presence = {name: name in serialized for name in required_parameters}
    semantic_presence = {term: term.lower() in lower for term in semantic_terms}
    passed = object_present and all(parameter_presence.values()) and all(semantic_presence.values())
    return {
        "status": "PASS" if passed else "HOLD",
        "class": "FRAMEWORK_SCHEMA_PASS" if passed else "FRAMEWORK_SCHEMA_EVIDENCE_INSUFFICIENT",
        "object_present": object_present,
        "required_parameters": parameter_presence,
        "semantic_terms": semantic_presence,
    }


def analyze_drift_schema_text(text: str, *, returncode: int = 0) -> dict[str, Any]:
    result = _schema_presence_analysis(
        text,
        returncode=returncode,
        object_type=DRIFT_TYPE,
        required_parameters=REQUIRED_FVFLUX_SCHEMA_PARAMETERS,
        semantic_terms=("FVFluxKernel",),
    )
    if result["status"] == "PASS":
        result.update(
            {
                "class": "FVFLUX_SCHEMA_PASS",
                "reason": "QPX object schema exposes FVFluxKernel boundary-execution controls and FVFluxKernel semantics",
            }
        )
    else:
        result.setdefault(
            "reason",
            "QPX object schema did not prove all required FVFluxKernel inheritance semantics",
        )
    return result


def analyze_constraint_schema_text(text: str, *, returncode: int = 0) -> dict[str, Any]:
    result = _schema_presence_analysis(
        text,
        returncode=returncode,
        object_type=CONSTRAINT_TYPE,
        required_parameters=REQUIRED_CONSTRAINT_SCHEMA_PARAMETERS,
        semantic_terms=("Lagrange multiplier",),
    )
    if result["status"] == "PASS":
        result.update(
            {
                "class": "FV_INVENTORY_CONSTRAINT_SCHEMA_PASS",
                "reason": "QPX schema exposes the FV integral-value constraint with variable/lambda/phi0 Lagrange-multiplier coupling",
            }
        )
    else:
        result.setdefault(
            "reason",
            "QPX object schema did not prove the required FV integral-value Lagrange-multiplier contract",
        )
    return result
