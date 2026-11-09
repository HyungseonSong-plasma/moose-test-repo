#!/usr/bin/env python3
"""Read-only, bounded external codeQA B1/B2/B3 + Python Mechanical pilot.

This is an experimental consumer of *existing* codeQA APIs, not a second
architecture evaluator or a MOOSE/FParser scientific acceptance check.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import traceback

from codeqa.adapters.python_dependencies import extract_parsed_dependencies
from codeqa.adapters.python_snapshot import parse_python_snapshot
from codeqa.evaluation.architecture.inventory import analyze_architecture_inventory
from codeqa.evaluation.architecture.metrics import analyze_architecture_metrics
from codeqa.evaluation.architecture.opportunities import discover_architecture_opportunities
from codeqa.evaluation.dependency_metrics import DependencyMetricsProfile
from codeqa.infrastructure.git import GitReader
from codeqa.infrastructure.resources import ResourceRegistry
from codeqa.pipeline.python import analyze_python

ROOT = Path(__file__).resolve().parents[2]
SELECTED_ROOTS = (
    "physics_harness/",
    "experiments/Issue282_e2a_rz_bridge/",
    "experiments/Issue471_ad_parser_runtime/",
    "physics_app/ci/",
)
FOCAL = (
    "physics_harness/execution/runtime.py",
    "physics_harness/execution/cases.py",
    "physics_harness/evidence/identity.py",
    "physics_harness/evidence/artifacts.py",
    "physics_harness/adapters/moose/preflight.py",
    "physics_harness/adapters/moose/check_input.py",
    "physics_harness/adapters/moose/source_inspection.py",
    "physics_harness/reasoning/diagnosis.py",
    "experiments/Issue471_ad_parser_runtime/diagnose_closure.py",
    "experiments/Issue282_e2a_rz_bridge/probe_parser_family.py",
    "experiments/Issue282_e2a_rz_bridge/diagnose_gdb_stack.py",
    "physics_app/ci/check_r2_o2_ionization_implementation.py",
    "physics_app/ci/check_r3_o2s_excitation_implementation.py",
)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def digest_bytes(blob: bytes) -> str:
    return sha256(blob).hexdigest()


def save(folder: Path, name: str, record: object) -> None:
    (folder / name).write_text(canonical_json(record), encoding="utf-8")


def projected_policy(source: dict) -> dict:
    """Projection of full module prefixes onto codeQA's first-level role graph.

    This is a pilot-only approximation: the Physics original has finer-grained
    module prefixes and operational exceptions, which are NOT reproduced here.
    """
    roles = source["roles"]
    converted = {}
    for name, definition in roles.items():
        forbidden = set()
        for raw in definition["forbidden_imports"]:
            if raw.startswith("physics_harness."):
                role = raw.split(".")[1]
                if role in roles:
                    forbidden.add(role)
        converted[name] = {
            "responsibility": definition["responsibility"],
            "forbidden_imports": sorted(forbidden),
        }
    return {
        "policy_id": source["policy_id"] + ".codeqa_first_level_projection",
        "schema_version": 1,
        "scope": "physics_harness",
        "roles": converted,
        "exceptions": [],
    }


def run(expected: str, codeqa_root: Path, output: Path) -> None:
    reader = GitReader(ROOT)
    current = reader._run("rev-parse", "HEAD").decode().strip()
    if current != expected:
        raise ValueError("checked-out target HEAD differs from expected immutable SHA")
    if len(expected) != 40:
        raise ValueError("un-pinned source revision")
    output.mkdir(parents=True, exist_ok=True)
    raw_policy_bytes = reader.read_file(current, "docs/architecture/physics_directory_roles_v1.json")
    original_policy = json.loads(raw_policy_bytes)
    role_policy = projected_policy(original_policy)
    save(output, "source-role-policy-projection.json", role_policy)

    # B1 has an explicit tracked scope; this is NOT repository-wide coverage.
    scoped = sorted(
        path for path in reader.tracked_paths()
        if path.startswith(SELECTED_ROOTS)
        and path.endswith((".py", ".md", ".json"))
    )
    if len(scoped) < len(FOCAL):
        raise ValueError("incomplete source selection")
    sources = {path: reader.read_file(current, path) for path in scoped}
    missing = sorted(set(FOCAL) - set(sources))
    if missing:
        raise ValueError("missing focal source: " + ",".join(missing))
    inventory = analyze_architecture_inventory(current, scoped, sources, role_policy)
    save(output, "b1-inventory.json", inventory)

    python_sources = {}
    unreadable = []
    for path in scoped:
        if path.endswith(".py"):
            try:
                python_sources[path] = sources[path].decode("utf-8")
            except UnicodeDecodeError:
                unreadable.append(path)
    parsed = parse_python_snapshot(python_sources)
    dependencies = extract_parsed_dependencies(parsed, snapshot_id=current)
    from dataclasses import replace
    dependencies = replace(
        dependencies,
        unprocessed_paths=tuple(sorted(set(dependencies.unprocessed_paths) | set(unreadable))),
    )

    registry = ResourceRegistry(codeqa_root)
    profile = DependencyMetricsProfile.from_mapping(
        registry.load_json("dependency_metrics_profile")
    )
    metrics = analyze_architecture_metrics(inventory, dependencies, role_policy, profile)
    save(output, "b2-metrics.json", metrics)
    opportunities = discover_architecture_opportunities(inventory, metrics)
    save(output, "b3-opportunities.json", opportunities)

    # Independent selected codeQA Mechanical pass. Findings are review flags.
    # No MOOSE C++ AST, runtime call tree or scientific method is analyzed.
    focus = {path: python_sources[path] for path in FOCAL}
    mechanical = analyze_python(
        focus, snapshot_id=current,
        ccg_schema=registry.load_json("ccg_schema"),
        mechanical_profile=registry.load_json("mechanical_profile"),
    )
    mechanical_summary = mechanical.summary_document()
    mechanical_findings = [asdict(f) for f in mechanical.quality.findings]
    save(output, "mechanical-summary.json", {
        **mechanical_summary,
        "findings": mechanical_findings[:100],
        "findings_truncated": len(mechanical_findings) > 100,
    })

    # Distinguish codeQA source witnesses from inferences and missing physics.
    declared_findings = metrics["declared_role_findings"]
    summary = {
        "schema": "physics471.codeqa_architecture_pilot.v0.1",
        "analysis_authority": "BOUNDED_PYTHON_STATIC_REVIEW_ONLY",
        "decision": "NOT_EVALUATED",
        "target_commit": current,
        "codeqa_commit": os.environ.get("EXPECTED_CODEQA_SHA"),
        "source_policy_sha256": digest_bytes(raw_policy_bytes),
        "policy_projection": "FIRST_LEVEL_ROLES_NOT_POLICY_EQUIVALENT",
        "policy_exceptions": "NOT_PROJECTED",
        "source_scope": list(SELECTED_ROOTS),
        "selected_tracked_text_files": len(scoped),
        "python_analyzed": metrics["coverage"]["python_analyzed"],
        "resolved_static_import_pairs": metrics["denominators"]["resolved_distinct_pairs"],
        "observed_static_cycles": len(metrics["cycles"]),
        "role_findings": declared_findings[:80],
        "role_findings_truncated": len(declared_findings) > 80,
        "architecture_opportunities": [
            {
                "family": s["family"],
                "scope_roles": s["scope_roles"],
                "measurement": s["measurement"],
                "witnesses": s["source_witnesses"][:20],
            }
            for s in opportunities["signals"]
        ],
        "mechanical_quality": mechanical_summary["quality"],
        "mechanical_review_findings": len(mechanical_findings),
        "known_unverified": [
            "FULL_REPOSITORY_COVERAGE_NOT_EVALUATED",
            "POLICY_FIRST_LEVEL_PROJECTION_NOT_EQUIVALENT",
            "APPROVED_OPERATIONAL_IMPORT_EXCEPTIONS_NOT_PROJECTED",
            "SOURCE_DOC_CONTRACT_CONTRADICTIONS_NOT_DETECTED",
            "DOCKER_COMPILER_ELF_ABI_JIT_NOT_ANALYZED",
            "CPP_MOOSE_NOT_ANALYZED",
            "RUNTIME_EXECUTION_NOT_EVALUATED",
            "SCIENTIFIC_ACCEPTANCE_NOT_EVALUATED",
            "EXTERNAL_CONSUMER_IMPACT_NOT_EVALUATED",
        ],
    }
    save(output, "pilot-summary.json", summary)
    integrity = {
        "target_commit": current,
        "codeqa_commit": os.environ.get("EXPECTED_CODEQA_SHA"),
        "items": [
            {"path": p.name, "sha256": digest_bytes(p.read_bytes())}
            for p in sorted(output.glob("*.json")) if p.name != "pilot-integrity.json"
        ],
    }
    save(output, "pilot-integrity.json", integrity)
    print("CODEQA_PILOT_" + "SUCCESS", "files", len(scoped), "modules",
          summary["python_analyzed"], "pairs",
          summary["resolved_static_import_pairs"], "signals",
          len(opportunities["signals"]), "status=NOT_EVALUATED")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expected-sha", required=True)
    p.add_argument("--codeqa-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        run(args.expected_sha, args.codeqa_root.resolve(), args.output.resolve())
    except Exception as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        save(args.output, "pilot-error.json", {
            "status": "INCONCLUSIVE_IMPLEMENTATION_OR_ENVIRONMENT",
            "error": repr(exc),
            "traceback": traceback.format_exc().splitlines()[-25:],
            "decision": "NOT_EVALUATED",
        })
        print("CODEQA_PILOT_INCONCLUSIVE:", repr(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
