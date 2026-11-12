"""Experimental *type-registration* projection for archived E2a inputs.

The current PhysicsApp registers canonical C++ object types where the frozen
historical Issue26 E2a builder emits seven QPX* type names. This module is
a strict reversible **type-token-only** research projection; after removal of
the electron lookup's legacy factory aliases and configurable coordinate,
its output is not guaranteed runnable without a separate, audited parameter
migration. It is NOT proof of parameter/algorithm/physics equivalence and is
NEVER the canonical SOL adapter contract.

No blocks, values, units, equations, boundaries, or initial conditions may
change. Both SHA256 versions are retained with the runtime evidence.
"""
from __future__ import annotations

import re

# The seven exact historical objects observed in the preserved P2 failure
# artifact #13507825610, with corresponding registered PhysicsApp C++ classes.
# Do not infer an alias from a prefix or auto-add new mappings.
HISTORICAL_TO_CURRENT_TYPE = {
    "QPXElectronTransportLookupMaterial": "DDMaterial",
    "QPXFVConservativeMassFractionTimeDerivative": "PhysicsFVConservativeMassFractionTimeDerivative",
    "QPXFVElectrostaticDrift": "PhysicsFVElectrostaticDrift",
    "QPXFVHeavyMassElectromigrationCorrection": "PhysicsFVHeavyMassElectromigrationCorrection",
    "QPXFVMassFractionAdvection": "PhysicsFVMassFractionAdvection",
    "QPXFVMixtureAveragedDiffusion": "PhysicsFVMixtureAveragedDiffusion",
    "QPXPlasmaChargeDensityMaterial": "PhysicsPlasmaChargeDensityMaterial",
}

TYPE_LINE = re.compile(
    r"(?m)^(?P<prefix>[ \t]*type[ \t]*=[ \t]*)(?P<name>[A-Za-z][A-Za-z0-9_]*)"
    r"(?P<suffix>[ \t]*(?:\#[^\r\n]*)?)$"
)


def project_historical_registration_only(text: str) -> tuple[str, dict]:
    """Fail closed on unrecognized legacy types; change type tokens *only*."""
    names = [m.group("name") for m in TYPE_LINE.finditer(text)]
    seen = {name for name in names if name.startswith("QPX")}
    if seen != set(HISTORICAL_TO_CURRENT_TYPE):
        raise ValueError(
            f"expected precisely seven historical QPX types: "
            f"missing={sorted(set(HISTORICAL_TO_CURRENT_TYPE) - seen)}, "
            f"unknown={sorted(seen - set(HISTORICAL_TO_CURRENT_TYPE))}"
        )
    counts = {k: names.count(k) for k in HISTORICAL_TO_CURRENT_TYPE}
    def replace(match: re.Match[str]) -> str:
        original = match.group("name")
        resolved = HISTORICAL_TO_CURRENT_TYPE.get(original, original)
        return match.group("prefix") + resolved + match.group("suffix")
    translated = TYPE_LINE.sub(replace, text)
    if translated == text:
        raise ValueError("no registration type substitutions produced")
    # Reverse all seven exact token substitutions to prove no other text edit.
    reverse = {v: k for k, v in HISTORICAL_TO_CURRENT_TYPE.items()}
    restored = TYPE_LINE.sub(
        lambda m: m.group("prefix")
        + reverse.get(m.group("name"), m.group("name"))
        + m.group("suffix"),
        translated,
    )
    if restored != text:
        raise ValueError("non-reversible research projection: source changed")
    if any(m.group("name").startswith("QPX") for m in TYPE_LINE.finditer(translated)):
        raise ValueError("legacy object remains in projected runtime input")
    return translated, {
        "status": "TYPE_TOKENS_ONLY_RESEARCH_PROJECTION",
        "not_physics_semantics_parity": True,
        "not_SOL_canonical": True,
        "mappings": {
            k: {"replacement": v, "instances": counts[k]}
            for k, v in HISTORICAL_TO_CURRENT_TYPE.items()
        },
    }
