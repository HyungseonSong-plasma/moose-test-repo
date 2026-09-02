from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

RESPONSIBILITY_CLASSES = frozenset(
    {
        "DATA",
        "DECLARATIVE_TRANSFORM",
        "ALGORITHM",
        "RUNTIME",
        "CHARACTERIZATION",
    }
)

RECIPE_BASELINES: dict[str, str] = {
    "recipes/issue31_coupling.py": "abf6679266c5f8d7cf53019743f44b6a78052f45",
    "recipes/issue43_coupling_diagnostic.py": "a57d2e1531b91f33ce7eb8a71a4e161193844dde",
    "recipes/issue43_fast_relaxation.py": "459a641a51358a030c81354decff585c48137c54",
    "recipes/issue45_first_linear.py": "0c787e4867cc4555ec7d6bfcb6a0b63768994ca3",
    "recipes/issue45_inventory_constraint.py": "f5b41b5f740ce78734c9c9410ba9b5c1c67a9751",
    "recipes/issue46_fd_reference.py": "96111bb968aa946e28565b412dfcd52b59d1ecaf",
    "recipes/issue46_jacobian_localization.py": "258955359c99b8ceeffe9d5d7320cea27ae37651",
}

FUNCTION_CLASSES: dict[str, dict[str, str]] = {
    "recipes/issue31_coupling.py": {
        "transport_only_input": "DECLARATIVE_TRANSFORM",
        "configured_transport_input": "DECLARATIVE_TRANSFORM",
        "_float": "ALGORITHM",
        "required_physics_columns": "ALGORITHM",
        "physics_csv": "RUNTIME",
        "physics_check": "ALGORITHM",
        "_result_status": "ALGORITHM",
        "_runtime_nonconvergence": "ALGORITHM",
        "_case_pass": "ALGORITHM",
        "_kg_e_pass": "ALGORITHM",
        "classify_evr2": "ALGORITHM",
    },
    "recipes/issue43_coupling_diagnostic.py": {
        "_ensure_debug_block": "DECLARATIVE_TRANSFORM",
        "instrument_input": "DECLARATIVE_TRANSFORM",
    },
    "recipes/issue43_fast_relaxation.py": {
        "_fmt": "DECLARATIVE_TRANSFORM",
        "_insert_top_level_before": "DECLARATIVE_TRANSFORM",
        "build_fast_input": "DECLARATIVE_TRANSFORM",
        "find_relaxation_csv": "RUNTIME",
        "read_relaxation_rows": "RUNTIME",
        "_state_scales": "ALGORITHM",
        "_distance": "ALGORITHM",
        "analyze_relaxation": "ALGORITHM",
        "_physics_pass": "ALGORITHM",
        "classify": "ALGORITHM",
    },
    "recipes/issue45_first_linear.py": {
        "instrument_first_linear": "DECLARATIVE_TRANSFORM",
        "_jacobian_analysis": "ALGORITHM",
        "_first_failed_reason": "ALGORITHM",
        "_runtime_core": "ALGORITHM",
        "_first_linear_termination": "ALGORITHM",
        "analyze_first_linear_text": "ALGORITHM",
    },
    "recipes/issue45_inventory_constraint.py": {
        "_truthy": "ALGORITHM",
        "_electron_kernel_records": "ALGORITHM",
        "_electron_fvbcs": "ALGORITHM",
        "_poisson_fvbcs": "ALGORITHM",
        "_flux_boundary_audit": "ALGORITHM",
        "_audit_poisson_grounding": "ALGORITHM",
        "_ensure_debug_block": "DECLARATIVE_TRANSFORM",
        "build_constrained_quasisteady_input": "DECLARATIVE_TRANSFORM",
        "_float_parameter": "ALGORITHM",
        "audit_constrained_quasisteady_structure": "ALGORITHM",
        "target_only_pair_audit": "ALGORITHM",
        "evaluate_runtime_case_data": "ALGORITHM",
        "evaluate_runtime_pair": "ALGORITHM",
    },
    "recipes/issue46_fd_reference.py": {
        "predict_fd_step_quantization": "ALGORITHM",
        "historical_evr1_prediction": "CHARACTERIZATION",
        "historical_mechanism_evidence": "CHARACTERIZATION",
        "_jacobian_analysis": "ALGORITHM",
        "_runtime_core_facts": "ALGORITHM",
        "termination_admissibility": "ALGORITHM",
        "runtime_mechanism_applicability": "ALGORITHM",
        "evidence_provenance_status": "ALGORITHM",
        "directional_localization": "ALGORITHM",
        "instrument_ds_reference": "DECLARATIVE_TRANSFORM",
        "remove_fd_type_pair": "DECLARATIVE_TRANSFORM",
        "mask_petsc_pair_lines": "DECLARATIVE_TRANSFORM",
        "analyze_ds_runtime": "ALGORITHM",
    },
    "recipes/issue46_jacobian_localization.py": {
        "_add_dofmap_output": "DECLARATIVE_TRANSFORM",
        "instrument_localization": "DECLARATIVE_TRANSFORM",
    },
}

SPEC_V1_TRANSFORM_READINESS: dict[tuple[str, str], str] = {
    ("recipes/issue31_coupling.py", "transport_only_input"): "PARTIAL",
    ("recipes/issue31_coupling.py", "configured_transport_input"): "PARTIAL",
    ("recipes/issue43_coupling_diagnostic.py", "_ensure_debug_block"): "YES",
    ("recipes/issue43_coupling_diagnostic.py", "instrument_input"): "YES",
    ("recipes/issue43_fast_relaxation.py", "_fmt"): "NO",
    ("recipes/issue43_fast_relaxation.py", "_insert_top_level_before"): "PARTIAL",
    ("recipes/issue43_fast_relaxation.py", "build_fast_input"): "PARTIAL",
    ("recipes/issue45_first_linear.py", "instrument_first_linear"): "YES",
    ("recipes/issue45_inventory_constraint.py", "_ensure_debug_block"): "YES",
    ("recipes/issue45_inventory_constraint.py", "build_constrained_quasisteady_input"): "PARTIAL",
    ("recipes/issue46_fd_reference.py", "instrument_ds_reference"): "YES",
    ("recipes/issue46_fd_reference.py", "remove_fd_type_pair"): "PARTIAL",
    ("recipes/issue46_fd_reference.py", "mask_petsc_pair_lines"): "NO",
    ("recipes/issue46_jacobian_localization.py", "_add_dofmap_output"): "YES",
    ("recipes/issue46_jacobian_localization.py", "instrument_localization"): "YES",
}

ALGORITHM_OWNER_OVERRIDES: dict[tuple[str, str], str] = {
    ("recipes/issue45_first_linear.py", "_jacobian_analysis"): "qpx_harness/diagnostics/jacobian.py",
    ("recipes/issue45_first_linear.py", "_runtime_core"): "qpx_harness/diagnostics/nonlinear_solver.py",
    ("recipes/issue46_fd_reference.py", "_jacobian_analysis"): "qpx_harness/diagnostics/jacobian.py",
    ("recipes/issue46_fd_reference.py", "_runtime_core_facts"): "qpx_harness/diagnostics/nonlinear_solver.py",
    ("recipes/issue46_fd_reference.py", "termination_admissibility"): "qpx_harness/diagnostics/termination.py",
    ("recipes/issue46_fd_reference.py", "runtime_mechanism_applicability"): "qpx_harness/evidence/runtime_identity.py",
    ("recipes/issue46_fd_reference.py", "evidence_provenance_status"): "qpx_harness/evidence/provenance.py",
    ("recipes/issue46_fd_reference.py", "directional_localization"): "qpx_harness/diagnostics/jacobian.py",
    ("recipes/issue45_inventory_constraint.py", "audit_constrained_quasisteady_structure"): "qpx_harness/diagnostics/moose_structure.py",
}

EXPECTED_MODULE_CONSUMER_SUBSETS: dict[str, set[str]] = {
    "recipes/issue31_coupling.py": {
        "qpx_harness/coupling_evr1/orchestration.py",
        "qpx_harness/coupling_evr2_runtime.py",
    },
    "recipes/issue43_coupling_diagnostic.py": {
        "qpx_harness/issue43_coupling/structure.py",
    },
    "recipes/issue43_fast_relaxation.py": {
        "qpx_harness/issue43_fast_base.py",
    },
    "recipes/issue45_first_linear.py": {
        "qpx_harness/issue45/first_linear_structure.py",
        "qpx_harness/issue46_jacobian_localization.py",
        "qpx_harness/issue46_fd_reference.py",
    },
    "recipes/issue46_jacobian_localization.py": {
        "qpx_harness/issue46_jacobian_localization.py",
        "qpx_harness/issue46_fd_reference.py",
    },
    "recipes/issue46_fd_reference.py": {
        "qpx_harness/issue46_fd_reference.py",
    },
}

CONSUMER_ROOTS = ("qpx_harness", "scripts", "tests")


class CensusError(RuntimeError):
    pass


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def recipe_module(path: str) -> str:
    return path[:-3].replace("/", ".")


def _assignment_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets: list[ast.expr]
    if isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        targets = list(node.targets)

    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            names.extend(item.id for item in target.elts if isinstance(item, ast.Name))
    return names


def top_level_symbols(path: Path) -> list[tuple[str, str]]:
    tree = ast.parse(path.read_text(), filename=str(path))
    result: list[tuple[str, str]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.append(("function", node.name))
        elif isinstance(node, ast.ClassDef):
            result.append(("class", node.name))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for name in _assignment_names(node):
                if not name.startswith("__"):
                    result.append(("data", name))
    return result


def classify_symbol(recipe_path: str, kind: str, name: str) -> str:
    if kind == "data":
        return "DATA"
    if kind == "class":
        if name.endswith("Error"):
            return "ALGORITHM"
        raise CensusError(
            f"unclassified top-level class {recipe_path}:{name}; "
            "assign an explicit responsibility before migration"
        )
    if kind == "function":
        try:
            value = FUNCTION_CLASSES[recipe_path][name]
        except KeyError as exc:
            raise CensusError(
                f"unclassified top-level function {recipe_path}:{name}"
            ) from exc
        if value not in RESPONSIBILITY_CLASSES:
            raise CensusError(
                f"invalid responsibility {value!r} for {recipe_path}:{name}"
            )
        return value
    raise CensusError(f"unknown symbol kind {kind!r}")


def spec_v1_readiness(
    recipe_path: str,
    kind: str,
    name: str,
    responsibility: str,
) -> str:
    if responsibility == "DATA":
        return "YES"
    if responsibility == "DECLARATIVE_TRANSFORM":
        return SPEC_V1_TRANSFORM_READINESS.get((recipe_path, name), "PARTIAL")
    return "NO"


def target_owner(recipe_path: str, name: str, responsibility: str) -> str | None:
    if responsibility == "DATA":
        return f"specs/experiments/{Path(recipe_path).stem}.json"
    if responsibility == "DECLARATIVE_TRANSFORM":
        return "qpx_harness/transforms/"
    if responsibility == "RUNTIME":
        return "qpx_harness/evidence/observation.py"
    if responsibility == "CHARACTERIZATION":
        return "qpx_harness/diagnostics/characterization.py"
    if responsibility == "ALGORITHM":
        return ALGORITHM_OWNER_OVERRIDES.get(
            (recipe_path, name),
            "recipe-policy (keep Python pending generic-capability proof)",
        )
    return None


def sensitivity(name: str, responsibility: str) -> str:
    if responsibility in {"DECLARATIVE_TRANSFORM", "ALGORITHM"}:
        return "HIGH"
    if responsibility in {"RUNTIME", "CHARACTERIZATION"}:
        return "MEDIUM"
    high_tokens = (
        "TARGET",
        "TOL",
        "DT",
        "PRESSURE",
        "ENERGY",
        "CHARGE",
        "EPS",
        "SPECIES",
        "EXPECTED",
        "BASELINE",
    )
    return "HIGH" if any(token in name.upper() for token in high_tokens) else "MEDIUM"


def _consumer_python_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for dirname in CONSUMER_ROOTS:
        base = root / dirname
        if not base.exists():
            continue
        paths.extend(path for path in base.rglob("*.py") if path.is_file())
    return sorted(set(paths))


def scan_consumers(
    root: Path,
    symbols_by_module: dict[str, set[str]],
) -> tuple[dict[str, set[str]], dict[tuple[str, str], set[str]]]:
    module_importers = {module: set() for module in symbols_by_module}
    symbol_consumers = {
        (module, symbol): set()
        for module, symbols in symbols_by_module.items()
        for symbol in symbols
    }
    short_to_module = {module.rsplit(".", 1)[-1]: module for module in symbols_by_module}

    for path in _consumer_python_paths(root):
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(), filename=rel)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            raise CensusError(f"cannot parse consumer {rel}: {exc}") from exc

        module_aliases: dict[str, str] = {}
        direct_aliases: dict[str, tuple[str, str]] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in symbols_by_module:
                        local = alias.asname or alias.name.split(".")[-1]
                        module_aliases[local] = alias.name
                        module_importers[alias.name].add(rel)
            elif isinstance(node, ast.ImportFrom):
                source = node.module or ""
                if source == "recipes":
                    for alias in node.names:
                        module = short_to_module.get(alias.name)
                        if module is None:
                            continue
                        local = alias.asname or alias.name
                        module_aliases[local] = module
                        module_importers[module].add(rel)
                elif source in symbols_by_module:
                    module_importers[source].add(rel)
                    for alias in node.names:
                        if alias.name == "*":
                            for symbol in symbols_by_module[source]:
                                symbol_consumers[(source, symbol)].add(rel)
                        elif alias.name in symbols_by_module[source]:
                            local = alias.asname or alias.name
                            direct_aliases[local] = (source, alias.name)
                            symbol_consumers[(source, alias.name)].add(rel)

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                module = module_aliases.get(node.value.id)
                if module is not None and node.attr in symbols_by_module[module]:
                    symbol_consumers[(module, node.attr)].add(rel)
            elif isinstance(node, ast.Name):
                target = direct_aliases.get(node.id)
                if target is not None:
                    symbol_consumers[target].add(rel)

    return module_importers, symbol_consumers


def build_census(root: Path = ROOT) -> dict[str, Any]:
    expected_recipe_names = {Path(path).name for path in RECIPE_BASELINES}
    observed_recipe_names = {
        path.name
        for path in (root / "recipes").glob("*.py")
        if path.name != "__init__.py"
    }
    recipe_set_ok = observed_recipe_names == expected_recipe_names

    module_symbols: dict[str, set[str]] = {}
    raw_symbols: dict[str, list[tuple[str, str]]] = {}
    sha_status: dict[str, dict[str, Any]] = {}

    for recipe_path, expected_sha in RECIPE_BASELINES.items():
        path = root / recipe_path
        if not path.is_file():
            raise CensusError(f"missing production recipe {recipe_path}")
        observed_sha = git_blob_sha(path)
        sha_status[recipe_path] = {
            "expected": expected_sha,
            "observed": observed_sha,
            "ok": observed_sha == expected_sha,
        }
        symbols = top_level_symbols(path)
        raw_symbols[recipe_path] = symbols
        module_symbols[recipe_module(recipe_path)] = {name for _, name in symbols}

    module_importers, symbol_consumers = scan_consumers(root, module_symbols)

    modules: list[dict[str, Any]] = []
    for recipe_path in sorted(RECIPE_BASELINES):
        module = recipe_module(recipe_path)
        records: list[dict[str, Any]] = []
        for kind, name in raw_symbols[recipe_path]:
            responsibility = classify_symbol(recipe_path, kind, name)
            consumers = sorted(symbol_consumers[(module, name)])
            importers = sorted(module_importers[module])
            compatibility = (
                "PRESERVE_SYMBOL_IMPORT_IDENTITY"
                if consumers
                else (
                    "PRESERVE_MODULE_SURFACE"
                    if importers
                    else "MODULE_INTERNAL_OR_ORPHAN_CANDIDATE"
                )
            )
            records.append(
                {
                    "symbol": name,
                    "kind": kind,
                    "responsibility": responsibility,
                    "issue_case_specific": True,
                    "spec_v1": spec_v1_readiness(
                        recipe_path,
                        kind,
                        name,
                        responsibility,
                    ),
                    "target_owner": target_owner(recipe_path, name, responsibility),
                    "compatibility": compatibility,
                    "scientific_runtime_sensitivity": sensitivity(
                        name,
                        responsibility,
                    ),
                    "consumers": consumers,
                    "module_importers": importers,
                }
            )
        modules.append(
            {
                "path": recipe_path,
                "module": module,
                "baseline": sha_status[recipe_path],
                "module_importers": sorted(module_importers[module]),
                "symbols": records,
            }
        )

    return {
        "issue": 59,
        "work_id": "qpx-experiment-spec-recipe-census",
        "recipe_set": {
            "expected": sorted(expected_recipe_names),
            "observed": sorted(observed_recipe_names),
            "ok": recipe_set_ok,
        },
        "modules": modules,
        "refactor_evrs": 0,
    }


def validate_census(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not payload["recipe_set"]["ok"]:
        errors.append(
            "production recipe set drift: "
            f"expected={payload['recipe_set']['expected']} "
            f"observed={payload['recipe_set']['observed']}"
        )

    observed_paths = {module["path"] for module in payload["modules"]}
    if observed_paths != set(RECIPE_BASELINES):
        errors.append("census module set does not match frozen production recipe set")

    for module in payload["modules"]:
        if not module["baseline"]["ok"]:
            errors.append(
                f"baseline drift {module['path']}: "
                f"{module['baseline']['observed']} != {module['baseline']['expected']}"
            )
        if not module["symbols"]:
            errors.append(f"no top-level symbols recorded for {module['path']}")
        for record in module["symbols"]:
            if record["responsibility"] not in RESPONSIBILITY_CLASSES:
                errors.append(
                    f"invalid responsibility {module['path']}:{record['symbol']}"
                )
            if record["spec_v1"] not in {"YES", "PARTIAL", "NO"}:
                errors.append(
                    f"invalid spec_v1 value {module['path']}:{record['symbol']}"
                )

    by_path = {module["path"]: module for module in payload["modules"]}
    for recipe_path, expected_subset in EXPECTED_MODULE_CONSUMER_SUBSETS.items():
        observed = set(by_path[recipe_path]["module_importers"])
        missing = expected_subset - observed
        if missing:
            errors.append(f"consumer scan missed {recipe_path}: {sorted(missing)}")

    pilot = by_path["recipes/issue43_coupling_diagnostic.py"]
    pilot_functions = [
        record for record in pilot["symbols"] if record["kind"] == "function"
    ]
    if not pilot_functions:
        errors.append("Issue43 coupling pilot has no function surface")
    for record in pilot_functions:
        if record["responsibility"] != "DECLARATIVE_TRANSFORM":
            errors.append(f"pilot function not declarative: {record['symbol']}")
        if record["spec_v1"] != "YES":
            errors.append(f"pilot function not v1-ready: {record['symbol']}")

    return errors


def self_test() -> None:
    assert classify_symbol(
        "recipes/issue43_coupling_diagnostic.py",
        "function",
        "instrument_input",
    ) == "DECLARATIVE_TRANSFORM"
    try:
        classify_symbol(
            "recipes/issue43_coupling_diagnostic.py",
            "function",
            "__unclassified_probe__",
        )
    except CensusError:
        pass
    else:
        raise AssertionError("unclassified function was not rejected")

    try:
        classify_symbol(
            "recipes/issue43_coupling_diagnostic.py",
            "class",
            "UnexpectedPolicy",
        )
    except CensusError:
        pass
    else:
        raise AssertionError("unclassified class was not rejected")

    assert spec_v1_readiness(
        "recipes/issue43_coupling_diagnostic.py",
        "function",
        "instrument_input",
        "DECLARATIVE_TRANSFORM",
    ) == "YES"
    assert spec_v1_readiness(
        "recipes/issue45_first_linear.py",
        "function",
        "_jacobian_analysis",
        "ALGORITHM",
    ) == "NO"


def main() -> int:
    payload = build_census()
    errors = validate_census(payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if errors:
        for error in errors:
            print(f"ISSUE59_CENSUS_ERROR: {error}")
        print("ISSUE59_CENSUS: FAIL")
        return 1
    print("ISSUE59_CENSUS: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
