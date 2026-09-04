"""QPX-free guard for legacy protocol specs and canonical semantic experiments."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.application.experiment_registry import protocol_registered
from qpx_harness.specification import SCHEMA_VERSION as SEMANTIC_SCHEMA_VERSION
from qpx_harness.specification import load_experiment_spec

# Historical schema-v1 operator surfaces remain explicit compatibility routes.
# Canonical schema-v2 experiments are deliberately NOT added here: a supported
# semantic experiment must require only JSON plus existing capabilities, never a
# new Issue-specific runner or protocol-registry entry.
CURRENT_OPERATOR_SURFACES = (
    (
        Path("Issue26_electron_energy/E1_zero_source/run.py"),
        Path("Issue26_electron_energy/E1_zero_source/experiment.json"),
        "issue26-electron-energy-e1",
    ),
    (
        Path("Issue26_electron_energy/E2a_controlled_diffusion/run.py"),
        Path("Issue26_electron_energy/E2a_controlled_diffusion/experiment.json"),
        "issue26-electron-energy-e2a",
    ),
    (
        Path("Issue26_electron_energy/E2b_E5_chain/run.py"),
        Path("Issue26_electron_energy/E2b_E5_chain/experiment.json"),
        "issue26-electron-energy-chain",
    ),
    (
        Path("Issue27_surface_reactions/controlled_wall/run.py"),
        Path("Issue27_surface_reactions/A1_o_recombination/experiment.json"),
        "issue27-surface-reaction-controlled-wall",
    ),
    (
        Path("Issue27_surface_reactions/controlled_wall/sticking.py"),
        Path("Issue27_surface_reactions/A1b_o_sticking/experiment.json"),
        "issue27-surface-reaction-controlled-wall",
    ),
    (
        Path("Issue27_surface_reactions/controlled_wall/multiwall.py"),
        Path("Issue27_surface_reactions/A1c_o_sticking_all_walls/experiment.json"),
        "issue27-surface-reaction-controlled-wall",
    ),
    (
        Path("Issue27_surface_reactions/controlled_wall/om.py"),
        Path("Issue27_surface_reactions/A2_om_neutralization/experiment.json"),
        "issue27-surface-reaction-controlled-wall",
    ),
    (
        Path("Issue27_surface_reactions/controlled_wall/positive.py"),
        Path("Issue27_surface_reactions/A3_positive_ion_neutralization/experiment.json"),
        "issue27-surface-reaction-controlled-wall",
    ),
    (
        Path("Issue27_surface_reactions/controlled_wall/charged.py"),
        Path("Issue27_surface_reactions/A3e_charged_wall_ledger/experiment.json"),
        "issue27-surface-reaction-controlled-wall",
    ),
    (
        Path("Issue27_surface_reactions/controlled_wall/excited.py"),
        Path("Issue27_surface_reactions/A4_excited_neutral_quenching/experiment.json"),
        "issue27-surface-reaction-controlled-wall",
    ),
    (
        Path("Issue27_surface_reactions/controlled_wall/combined.py"),
        Path("Issue27_surface_reactions/A6_combined_wall_integration/experiment.json"),
        "issue27-surface-reaction-controlled-wall",
    ),
    (
        Path("Issue27_surface_reactions/controlled_wall/electron_wall_stable.py"),
        Path("Issue27_surface_reactions/A7_comsol_electron_wall/experiment.json"),
        "issue27-surface-reaction-controlled-wall",
    ),
    (
        Path("Issue27_surface_reactions/controlled_wall/see.py"),
        Path("Issue27_surface_reactions/A8_finite_see/experiment.json"),
        "issue27-surface-reaction-controlled-wall",
    ),
    (
        Path("R3_electron_master_diagnostic/run.py"),
        Path("R3_electron_master_diagnostic/experiment.json"),
        "r3-electron-master-diagnostic",
    ),
    (
        Path("R3_electron_scaling_counterfactual/run.py"),
        Path("R3_electron_scaling_counterfactual/experiment.json"),
        "r3-electron-scaling-counterfactual",
    ),
    (
        Path("R3_fv_internal_completion/run.py"),
        Path("R3_fv_internal_completion/experiment.json"),
        "r3-fv-internal-completion",
    ),
    (
        Path("Issue31_r4_qf2_local_charge_relaxation/run.py"),
        Path("Issue31_r4_qf2_local_charge_relaxation/experiment.json"),
        "r4-qf2-local-charge-relaxation",
    ),
)


def _load_raw(spec: Path, errors: list[str]) -> dict[str, object] | None:
    try:
        raw = json.loads(spec.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{spec.relative_to(ROOT)}: invalid JSON: {exc}")
        return None
    if not isinstance(raw, dict):
        errors.append(f"{spec.relative_to(ROOT)}: experiment JSON must be an object")
        return None
    return raw


def main() -> int:
    errors: list[str] = []
    legacy_specs: set[Path] = set()

    for relative_runner, relative_spec, expected_protocol in sorted(
        CURRENT_OPERATOR_SURFACES,
        key=lambda item: str(item[1]),
    ):
        runner = EXPERIMENTS / relative_runner
        spec = EXPERIMENTS / relative_spec
        legacy_specs.add(spec.resolve())
        if not runner.is_file():
            errors.append(f"experiments/{relative_runner}: registered operator runner missing")
            continue
        if not spec.is_file():
            errors.append(f"experiments/{relative_spec}: registered operator spec missing")
            continue
        raw = _load_raw(spec, errors)
        if raw is None:
            continue
        if raw.get("schema_version") != 1:
            errors.append(f"{spec.relative_to(ROOT)}: legacy protocol schema_version must be 1")
        protocol = raw.get("protocol")
        if protocol != expected_protocol:
            errors.append(
                f"{spec.relative_to(ROOT)}: expected protocol {expected_protocol!r}, got {protocol!r}"
            )
        if isinstance(protocol, str) and not protocol_registered(protocol):
            errors.append(f"{spec.relative_to(ROOT)}: protocol {protocol!r} is not registered")

    discovered_specs = {spec.resolve() for spec in EXPERIMENTS.glob("**/experiment.json")}
    semantic_specs: set[Path] = set()

    for spec_resolved in sorted(discovered_specs - legacy_specs):
        spec = Path(spec_resolved)
        raw = _load_raw(spec, errors)
        if raw is None:
            continue
        if raw.get("schema_version") != SEMANTIC_SCHEMA_VERSION:
            errors.append(
                f"{spec.relative_to(ROOT)}: unclassified declarative experiment; "
                f"expected canonical semantic schema_version={SEMANTIC_SCHEMA_VERSION}"
            )
            continue
        if "protocol" in raw:
            errors.append(
                f"{spec.relative_to(ROOT)}: canonical semantic experiment must not own a protocol route"
            )
            continue
        try:
            load_experiment_spec(spec)
        except Exception as exc:
            errors.append(f"{spec.relative_to(ROOT)}: invalid canonical semantic spec: {exc}")
            continue
        semantic_specs.add(spec_resolved)

    classified = legacy_specs | semantic_specs
    for spec_resolved in sorted(discovered_specs - classified):
        spec = Path(spec_resolved)
        if not any(str(spec.relative_to(ROOT)) in error for error in errors):
            errors.append(
                f"{spec.relative_to(ROOT)}: declarative experiment exists but is neither "
                "a registered schema-v1 compatibility route nor a valid schema-v2 semantic spec"
            )

    if errors:
        print("EXPERIMENT_GATEWAY_FAIL")
        print("\n".join(errors))
        return 1
    print(
        "EXPERIMENT_GATEWAY_PASS "
        f"legacy_specs={len(legacy_specs)} semantic_specs={len(semantic_specs)} "
        "semantic_protocol_entries=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
