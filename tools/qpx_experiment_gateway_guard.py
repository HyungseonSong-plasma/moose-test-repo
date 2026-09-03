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

CURRENT_OPERATOR_RUNNERS = {
    Path("R3_electron_master_diagnostic/run.py"): "r3-electron-master-diagnostic",
    Path("R3_electron_scaling_counterfactual/run.py"): "r3-electron-scaling-counterfactual",
    Path("R3_fv_internal_completion/run.py"): "r3-fv-internal-completion",
    Path("Issue31_r4_qf2_local_charge_relaxation/run.py"): "r4-qf2-local-charge-relaxation",
}


def _spec_path(relative_runner: Path) -> Path:
    return EXPERIMENTS / relative_runner.parent / "experiment.json"


def main() -> int:
    errors: list[str] = []
    for relative_runner, expected_protocol in sorted(CURRENT_OPERATOR_RUNNERS.items(), key=lambda item: str(item[0])):
        runner = EXPERIMENTS / relative_runner
        spec = _spec_path(relative_runner)
        if not runner.is_file():
            errors.append(f"experiments/{relative_runner}: registered operator runner missing")
            continue
        if not spec.is_file():
            errors.append(f"experiments/{relative_runner}: active operator runner has no sibling experiment.json")
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

    for spec in sorted(EXPERIMENTS.glob("**/experiment.json")):
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
    print(f"EXPERIMENT_GATEWAY_PASS active_specs={len(CURRENT_OPERATOR_RUNNERS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
