"""QPX-free guard for the canonical schema-v2 experiment control plane."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
APPLICATION = ROOT / "qpx_harness" / "application"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.specification import SCHEMA_VERSION, load_experiment_spec

FORBIDDEN_PRODUCTION_PATHS = (
    APPLICATION / "experiment_registry.py",
    APPLICATION / "experiment_service.py",
    APPLICATION / "experiment_spec.py",
    APPLICATION / "protocols",
)


def _raw(path: Path, errors: list[str]) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{path.relative_to(ROOT)}: experiment JSON must be an object")
        return None
    return value


def main() -> int:
    errors: list[str] = []

    for path in FORBIDDEN_PRODUCTION_PATHS:
        if path.exists():
            errors.append(
                f"{path.relative_to(ROOT)}: retired schema-v1 protocol ownership remains in production"
            )

    semantic_specs = 0
    historical_specs = 0
    for spec in sorted(EXPERIMENTS.glob("**/experiment.json")):
        raw = _raw(spec, errors)
        if raw is None:
            continue
        version = raw.get("schema_version")
        if version == SCHEMA_VERSION:
            if "protocol" in raw:
                errors.append(
                    f"{spec.relative_to(ROOT)}: canonical schema-v2 experiment must not declare protocol"
                )
                continue
            try:
                load_experiment_spec(spec)
            except Exception as exc:
                errors.append(f"{spec.relative_to(ROOT)}: invalid canonical semantic spec: {exc}")
                continue
            semantic_specs += 1
        elif version == 1:
            # Historical experiment fixtures may remain immutable provenance, but
            # they are not executable through the canonical application/CLI path.
            historical_specs += 1
        else:
            errors.append(
                f"{spec.relative_to(ROOT)}: unsupported experiment schema_version={version!r}"
            )

    cli = (ROOT / "qpx_harness" / "cli" / "app.py").read_text(encoding="utf-8")
    forbidden_cli_tokens = (
        "run_experiment(",
        "from qpx_harness.application import normalize_temporal_run_csv, preflight_input, run_experiment",
        "resolve_protocol",
        "protocol_registered",
    )
    for token in forbidden_cli_tokens:
        if token in cli:
            errors.append(f"qpx_harness/cli/app.py: forbidden legacy experiment dispatch token {token!r}")

    if errors:
        print("EXPERIMENT_CONTROL_PLANE_GUARD: FAIL")
        print("\n".join(errors))
        return 1

    print(
        "EXPERIMENT_CONTROL_PLANE_GUARD: PASS "
        f"schema_version={SCHEMA_VERSION} canonical_specs={semantic_specs} "
        f"historical_schema_v1_fixtures={historical_specs} protocol_dispatch=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
