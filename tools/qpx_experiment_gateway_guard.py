"""QPX-free guard for current operator-facing declarative experiments."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.application.experiment_registry import protocol_registered

# Each tuple freezes one current operator-facing experiment surface as
# (implementation runner, declarative spec, protocol id). Runner and spec are
# deliberately separate: one protocol may own several bounded experiment
# instances, and Issue27 dispatches prescribed/sticking/charged wall models
# through the same application protocol.
CURRENT_OPERATOR_SURFACES = (
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
        Path("Issue27_surface_reactions/controlled_wall/electron_wall.py"),
        Path("Issue27_surface_reactions/A7_comsol_electron_wall/experiment.json"),
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


def main() -> int:
    errors: list[str] = []
    declared_specs: set[Path] = set()
    for relative_runner, relative_spec, expected_protocol in sorted(
        CURRENT_OPERATOR_SURFACES,
        key=lambda item: str(item[1]),
    ):
        runner = EXPERIMENTS / relative_runner
        spec = EXPERIMENTS / relative_spec
        declared_specs.add(spec.resolve())
        if not runner.is_file():
            errors.append(f"experiments/{relative_runner}: registered operator runner missing")
            continue
        if not spec.is_file():
            errors.append(f"experiments/{relative_spec}: registered operator spec missing")
            continue
        try:
            raw = json.loads(spec.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{spec.relative_to(ROOT)}: invalid JSON: {exc}")
            continue
        if raw.get("schema_version") != 1:
            errors.append(f"{spec.relative_to(ROOT)}: schema_version must be 1")
        protocol = raw.get("protocol")
        if protocol != expected_protocol:
            errors.append(
                f"{spec.relative_to(ROOT)}: expected protocol {expected_protocol!r}, got {protocol!r}"
            )
        if isinstance(protocol, str) and not protocol_registered(protocol):
            errors.append(f"{spec.relative_to(ROOT)}: protocol {protocol!r} is not registered")

    discovered_specs = {spec.resolve() for spec in EXPERIMENTS.glob("**/experiment.json")}
    undeclared = sorted(discovered_specs - declared_specs)
    for spec_resolved in undeclared:
        spec = Path(spec_resolved)
        errors.append(
            f"{spec.relative_to(ROOT)}: declarative experiment exists but is not classified "
            "in CURRENT_OPERATOR_SURFACES"
        )

    for spec_resolved in sorted(discovered_specs):
        spec = Path(spec_resolved)
        try:
            raw = json.loads(spec.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{spec.relative_to(ROOT)}: invalid JSON: {exc}")
            continue
        protocol = raw.get("protocol") if isinstance(raw, dict) else None
        if not isinstance(protocol, str) or not protocol_registered(protocol):
            errors.append(f"{spec.relative_to(ROOT)}: unregistered protocol {protocol!r}")

    if errors:
        print("EXPERIMENT_GATEWAY_FAIL")
        print("\n".join(errors))
        return 1
    print(f"EXPERIMENT_GATEWAY_PASS active_specs={len(CURRENT_OPERATOR_SURFACES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
