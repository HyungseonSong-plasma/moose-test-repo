"""Physics guard for the canonical schema-v2 experiment control plane."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
APPLICATION = ROOT / "physics_harness" / "application"
GUIDES = ROOT / "docs" / "guides"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics_harness.specification import SCHEMA_VERSION, load_experiment_spec

FORBIDDEN_PRODUCTION_PATHS = (
    APPLICATION / "experiment_registry.py",
    APPLICATION / "experiment_service.py",
    APPLICATION / "protocols",
)
HISTORICAL_DECODER = APPLICATION / "experiment_spec.py"

# These spellings belonged to the retired schema-v1/QPX protocol-dispatch control
# plane.  Historical architecture/development records may quote them, but current
# operator-facing guides and experiment READMEs must not present them as runnable
# instructions.  This closes the documentation escape left by the #147 migration.
RETIRED_OPERATOR_TOKENS = (
    "python qpx",
    "qpx -e",
    "qpx -i",
    "python physics -e",
    "python3 physics -e",
    "bin/physics.py -e",
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


def _retired_operator_tokens(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    return tuple(token for token in RETIRED_OPERATOR_TOKENS if token in lowered)


def _operator_doc_guard(errors: list[str]) -> int:
    # P0 mutation controls for the guard itself.  The check must reject both the
    # former QPX spelling and the later-but-retired Physics -e spelling, while
    # allowing the current semantic command family and historical product name.
    negative_controls = (
        "python qpx -i all",
        "python qpx -e experiments/old/experiment.json",
        "qpx -e experiments/old/experiment.json",
        "python physics -e experiments/old/experiment.json",
        "python3 bin/physics.py -e experiments/old/experiment.json",
    )
    positive_controls = (
        "python3 bin/physics.py compile experiments/semantic/example/experiment.json",
        "python3 bin/physics.py plan experiments/semantic/example/experiment.json",
        "python3 bin/physics.py lower experiments/semantic/example/experiment.json",
        "python3 bin/physics.py run experiments/semantic/example/experiment.json",
        "QPX is a historical product/repository name.",
    )
    for sample in negative_controls:
        if not _retired_operator_tokens(sample):
            errors.append(f"operator-doc guard self-test missed retired instruction: {sample!r}")
    for sample in positive_controls:
        if _retired_operator_tokens(sample):
            errors.append(f"operator-doc guard self-test rejected current/historical prose: {sample!r}")

    paths = set(GUIDES.glob("*.md"))
    paths.update(EXPERIMENTS.glob("**/README.md"))
    for path in sorted(paths):
        text = path.read_text(encoding="utf-8")
        tokens = _retired_operator_tokens(text)
        if tokens:
            errors.append(
                f"{path.relative_to(ROOT)}: retired executable experiment instruction(s) "
                f"remain in an operator-facing document: {', '.join(tokens)}"
            )
    return len(paths)


def main() -> int:
    errors: list[str] = []

    for path in FORBIDDEN_PRODUCTION_PATHS:
        if path.exists():
            errors.append(
                f"{path.relative_to(ROOT)}: retired schema-v1 protocol ownership remains in production"
            )

    if HISTORICAL_DECODER.is_file():
        decoder = HISTORICAL_DECODER.read_text(encoding="utf-8")
        for token in ("ExperimentControl", "resolve_protocol", "protocol_registered", "run_experiment"):
            if token in decoder:
                errors.append(
                    f"{HISTORICAL_DECODER.relative_to(ROOT)}: historical decoder contains control-plane token {token!r}"
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
            # Schema-v1 files are immutable historical provenance/characterization
            # fixtures only.  They are deliberately not dispatched here.
            historical_specs += 1
        else:
            errors.append(
                f"{spec.relative_to(ROOT)}: unsupported experiment schema_version={version!r}"
            )

    cli = (ROOT / "physics_harness" / "cli" / "app.py").read_text(encoding="utf-8")
    forbidden_cli_tokens = (
        "run_experiment(",
        "resolve_protocol",
        "protocol_registered",
    )
    for token in forbidden_cli_tokens:
        if token in cli:
            errors.append(f"physics_harness/cli/app.py: forbidden legacy experiment dispatch token {token!r}")

    application_init = (APPLICATION / "__init__.py").read_text(encoding="utf-8")
    if "load_experiment_spec" in application_init or "HistoricalExperimentFixture" in application_init:
        errors.append("physics_harness/application/__init__.py: historical fixture decoder must not be canonical application API")

    operator_docs_scanned = _operator_doc_guard(errors)

    if errors:
        print("EXPERIMENT_CONTROL_PLANE_GUARD: FAIL")
        print("\n".join(errors))
        return 1

    print(
        "EXPERIMENT_CONTROL_PLANE_GUARD: PASS "
        f"schema_version={SCHEMA_VERSION} canonical_specs={semantic_specs} "
        f"historical_schema_v1_fixtures={historical_specs} protocol_dispatch=0 "
        f"operator_docs_scanned={operator_docs_scanned} retired_operator_instructions=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
