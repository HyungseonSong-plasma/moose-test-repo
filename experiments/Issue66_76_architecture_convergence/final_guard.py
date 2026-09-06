from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.historical_recipe_support import issue43_coupling_diagnostic as issue43_recipe
from experiments.historical_recipe_support import issue45_first_linear as issue45_recipe
from experiments.historical_recipe_support import issue46_jacobian_localization as issue46_loc_recipe
from qpx_harness.cli.app import COMMANDS, main as cli_main
from qpx_harness.evidence import artifacts as evidence_artifacts
from qpx_harness.execution import cases as execution_cases
from qpx_harness.execution import runtime as execution_runtime
from qpx_harness.execution import workspace as execution_workspace
from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp
from qpx_harness.adapters.moose.input import MooseInput
from qpx_harness.petsc import options as po
from qpx_harness.adapters.moose.mutation_spec import MutationSpecError, compile_mutation_spec, load_mutation_json_file, load_mutation_payload
from qpx_harness.adapters.moose.mutation_spec.plan import OperationPlan
from qpx_harness.adapters.moose.transforms import SUPPORTED_OPERATIONS, TransformError, apply_operation

EXPECTED_OPERATIONS = {
    "ensure_block",
    "set_parameter",
    "add_petsc_flags",
    "remove_block",
    "replace_block",
    "insert_child_block",
    "insert_top_level_before",
    "remove_paths",
    "remove_petsc_flags",
    "set_petsc_option",
    "remove_petsc_option",
}
EXPECTED_COMMANDS = {
    "test",
    "test-all",
    "coupling-evr1",
    "coupling-evr2",
    "scale-audit",
    "fast-relaxation",
    "fast-coupling-diagnostic",
    "inventory-nullspace",
    "inventory-first-linear",
    "inventory-jacobian-localization",
    "inventory-fd-reference",
    "contract",
    "dmix-equivalence",
    "measure",
    "measure-smoke",
    "investigate",
    "transport-probe",
    "cache-audit",
    "profile",
    "analyze",
    "bundle",
    "inventory",
    "preflight",
    "temporal-csv",
    "self-test",
}
OWNERSHIP_MODELS = {
    "SPEC_OWNED_COMPAT_ADAPTER",
    "HYBRID_SPEC_PLUS_PYTHON_POLICY",
    "PURE_PYTHON_SCIENTIFIC_POLICY",
    "RETIRED_AFTER_CONSUMER_PROOF",
}
SPEC_PATHS = (
    ROOT / "specs" / "experiments" / "issue43_coupling_diagnostic.json",
    ROOT / "specs" / "experiments" / "issue45_first_linear.json",
    ROOT / "specs" / "experiments" / "issue46_jacobian_localization.json",
)
OWNERSHIP_PATH = ROOT / "docs" / "development" / "2026-09-01_issue73_recipe_ownership.json"
CENSUS_PATH = ROOT / "tools" / "qpx_architecture_census.py"
BIN_QPX = ROOT / "bin" / "qpx.py"

SYNTHETIC = """[Variables]
  [u]
    type = MooseVariableFVReal
  []
  [drop]
    type = MooseVariableFVReal
  []
[]
[FVKernels]
  [keep]
    type = FVDiffusion
    variable = u
  []
  [drop_kernel]
    type = FVDiffusion
    variable = drop
  []
[]
[Executioner]
  type = Transient
  petsc_options = '-keep -remove'
  petsc_options_iname = '-pc_type -mat_fd_type'
  petsc_options_value = 'lu wp'
[]
[Outputs]
  [console]
    type = Console
  []
[]
"""

FIRST_LINEAR_BASE = """[Executioner]
  type = Steady
  petsc_options = '-existing'
[]
[Outputs]
  [console]
    type = Console
  []
[]
"""

LOCALIZATION_BASE = """[Executioner]
  type = Steady
  nl_max_its = 1
  petsc_options = '-snes_converged_reason -snes_test_jacobian -ksp_view'
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]
[Outputs]
  [console]
    type = Console
  []
[]
"""

COUPLING_BASE = """[Executioner]
  type = Transient
  petsc_options = '-existing'
[]
[Outputs]
  [console]
    type = Console
  []
[]
"""


def _legacy_issue43(text: str, *, jacobian_test: bool) -> str:
    if not mb.has_block(text, "Debug"):
        out = mb.append_top_level_block(
            text,
            "[Debug]\n  show_var_residual_norms = true\n[]",
        )
    else:
        out = mp.upsert_parameter(text, "Debug", "show_var_residual_norms", "true")
    out = mp.upsert_parameter(out, "Executioner", "verbose", "true")
    flags = (
        "-snes_converged_reason",
        "-ksp_converged_reason",
        "-snes_monitor",
        "-ksp_monitor",
    )
    if jacobian_test:
        flags += ("-snes_test_jacobian",)
    out = po.add_flags(out, flags)
    return mp.upsert_parameter(out, "Outputs/console", "all_variable_norms", "true")


def _legacy_issue45(text: str) -> str:
    out = mp.upsert_parameter(text, "Executioner", "nl_max_its", "1")
    return po.add_flags(
        out,
        (
            "-snes_converged_reason",
            "-ksp_converged_reason",
            "-snes_test_jacobian",
            "-ksp_view",
            "-ksp_monitor_true_residual",
        ),
    )


def _legacy_issue46_localization(text: str) -> str:
    out = po.remove_flags(text, ["-snes_test_jacobian"])
    out = po.add_flags(out, ["-snes_test_jacobian_view"])
    out = po.upsert_name_value(out, "-snes_test_jacobian", "1e-07")
    block = """  [r46_dofmap]
    type = DOFMap
    execute_on = INITIAL
    file_base = r46_dofmap
  []"""
    return mb.insert_child_block(out, "Outputs", block)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def main() -> int:
    failures: list[str] = []

    # #66: strict bounded vocabulary and every new transform independently characterized.
    try:
        assert set(SUPPORTED_OPERATIONS) == EXPECTED_OPERATIONS
        invalid = {
            "schema_version": 1,
            "experiment_id": "bad",
            "cases": [{"case_id": "bad", "operations": [{"op": "arbitrary_python"}]}],
        }
        try:
            load_mutation_payload(invalid)
        except MutationSpecError:
            pass
        else:
            raise AssertionError("unknown operation accepted")

        text = apply_operation(SYNTHETIC, OperationPlan("remove_block", (("path", "FVKernels/drop_kernel"),)))
        assert not mb.has_block(text, "FVKernels/drop_kernel")
        text = apply_operation(
            text,
            OperationPlan(
                "replace_block",
                (("path", "FVKernels/keep"), ("block", "  [keep]\n    type = FVDiffusion\n    variable = u\n    coeff = 2\n  []")),
            ),
        )
        assert mp.get_parameter(text, "FVKernels/keep", "coeff") == "2"
        text = apply_operation(
            text,
            OperationPlan(
                "insert_child_block",
                (("parent", "Outputs"), ("path", "Outputs/new_console"), ("block", "  [new_console]\n    type = Console\n  []")),
            ),
        )
        assert mb.has_block(text, "Outputs/new_console")
        text = apply_operation(
            text,
            OperationPlan(
                "insert_top_level_before",
                (("marker", "Outputs"), ("block", "[Debug]\n  show_var_residual_norms = true\n[]")),
            ),
        )
        assert text.index("[Debug]") < text.index("[Outputs]")
        text = apply_operation(text, OperationPlan("remove_paths", (("paths", ("Variables/drop",)),)))
        assert not mb.has_block(text, "Variables/drop")
        text = apply_operation(
            text,
            OperationPlan(
                "remove_petsc_flags",
                (("flags", ("-remove",)), ("path", "Executioner"), ("parameter", "petsc_options")),
            ),
        )
        assert "-remove" not in po.get_flags(text)
        text = apply_operation(
            text,
            OperationPlan(
                "set_petsc_option",
                (("name", "-mat_fd_type"), ("value", "ds"), ("path", "Executioner"), ("names_parameter", "petsc_options_iname"), ("values_parameter", "petsc_options_value")),
            ),
        )
        assert ("-mat_fd_type", "ds") in po.get_name_value_pairs(text)
        text = apply_operation(
            text,
            OperationPlan(
                "remove_petsc_option",
                (("name", "-mat_fd_type"), ("path", "Executioner"), ("names_parameter", "petsc_options_iname"), ("values_parameter", "petsc_options_value")),
            ),
        )
        assert all(name != "-mat_fd_type" for name, _ in po.get_name_value_pairs(text))
    except Exception as exc:
        failures.append(f"Issue66 bounded transform vocabulary: {exc}")
        print(f"ISSUE66_BOUNDED_TRANSFORMS: FAIL ({exc})")
    else:
        print("ISSUE66_BOUNDED_TRANSFORMS: PASS operations=11")

    # #67/#68: specs validate, legacy rendering remains byte-identical, reusable diagnostics own mechanics.
    try:
        for path in SPEC_PATHS:
            plan = compile_mutation_spec(load_mutation_json_file(path))
            assert plan.schema_version == 1
        for jacobian in (False, True):
            rendered, _ = issue43_recipe.instrument_input(COUPLING_BASE, jacobian_test=jacobian)
            assert rendered == _legacy_issue43(COUPLING_BASE, jacobian_test=jacobian)
        rendered45, _ = issue45_recipe.instrument_first_linear(FIRST_LINEAR_BASE)
        assert rendered45 == _legacy_issue45(FIRST_LINEAR_BASE)
        rendered46, _ = issue46_loc_recipe.instrument_localization(LOCALIZATION_BASE)
        assert rendered46 == _legacy_issue46_localization(LOCALIZATION_BASE)

        diagnostics_root = ROOT / "qpx_harness" / "diagnostics"
        diagnostic_imports = set().union(*(_imports(path) for path in diagnostics_root.glob("*.py")))
        assert not any(module.startswith("recipes") for module in diagnostic_imports)
        assert not any(module.startswith("qpx_harness.issue") for module in diagnostic_imports)
        issue43_analysis = (ROOT / "qpx_harness" / "issue43_coupling" / "analysis.py").read_text()
        issue45_source = (ROOT / "recipes" / "issue45_first_linear.py").read_text()
        assert "jacobian_diagnostic.analyze_comparisons" in issue43_analysis
        assert "nonlinear_diagnostic.runtime_core_facts" in issue43_analysis
        assert "qpx_harness.diagnostics" in issue45_source
    except Exception as exc:
        failures.append(f"Issue67/68 spec and diagnostics convergence: {exc}")
        print(f"ISSUE67_68_SPEC_DIAGNOSTICS: FAIL ({exc})")
    else:
        print("ISSUE67_68_SPEC_DIAGNOSTICS: PASS legacy/spec byte-identical")

    # #70/#72/#73/#77: machine census, capability owners, facade retirement, recipe terminal ownership.
    try:
        census_module = _load_module(CENSUS_PATH, "issue70_census")
        census = census_module.build_census()
        assert census["status"] == "PASS", census
        assert census["generic_to_issue_edges"] == []
        assert census["unclassified"] == []

        for retired in ("artifacts.py", "cases.py", "runtime.py", "workspace.py"):
            assert not (HERE / retired).exists(), retired
        assert execution_runtime.run_qpx
        assert execution_runtime.resolve_executable
        assert execution_cases.stage_case
        assert execution_cases.validate_case_references
        assert execution_workspace.discover_manifests
        assert execution_workspace.inventory_workspace
        assert evidence_artifacts.write_json_bundle
        assert evidence_artifacts.current_run_artifact

        ownership = json.loads(OWNERSHIP_PATH.read_text())
        recipes = ownership["recipes"]
        expected_recipe_paths = sorted(
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "recipes").glob("issue*.py")
        )
        assert sorted(recipes) == expected_recipe_paths
        for path, record in recipes.items():
            assert record["model"] in OWNERSHIP_MODELS, (path, record)
            spec_path = record.get("spec")
            if spec_path:
                compile_mutation_spec(load_mutation_json_file(ROOT / spec_path))
    except Exception as exc:
        failures.append(f"Issue70/72/73 ownership convergence: {exc}")
        print(f"ISSUE70_72_73_OWNERSHIP: FAIL ({exc})")
    else:
        print("ISSUE70_72_73_OWNERSHIP: PASS")

    # #74/#75: command inventory preserved, bin is canonical, scripts retired with current-surface proof.
    try:
        assert set(COMMANDS) == EXPECTED_COMMANDS
        assert len(COMMANDS) == 25
        launcher = BIN_QPX.read_text()
        assert "from qpx_harness.cli import main" in launcher
        assert "COMMANDS" not in launcher
        assert "argparse" not in launcher
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            assert cli_main(["help"]) == 0
            assert cli_main(["definitely-not-a-command"]) == 2

        assert not (ROOT / "scripts").exists(), "transitional scripts/ directory still exists"
        current_surfaces = [
            ROOT / "README.md",
            ROOT / "WORKSPACE.md",
            ROOT / "BOOTSTRAP.md",
            ROOT / "OPERATING_CORE.md",
            ROOT / "PROTOCOL_INDEX.md",
            ROOT / "docs" / "protocols",
            ROOT / "tests" / "README.md",
            ROOT / ".github",
        ]
        stale: list[str] = []
        for surface in current_surfaces:
            paths = [surface] if surface.is_file() else sorted(surface.rglob("*"))
            for path in paths:
                if not path.is_file() or path.suffix.lower() not in {"", ".md", ".txt", ".py", ".yml", ".yaml"}:
                    continue
                try:
                    content = path.read_text(errors="replace")
                except OSError:
                    continue
                if "scripts/qpx.py" in content or "temp/scripts/qpx.py" in content:
                    stale.append(path.relative_to(ROOT).as_posix())
        assert not stale, stale
    except Exception as exc:
        failures.append(f"Issue74/75 CLI and scripts retirement: {exc}")
        print(f"ISSUE74_75_CLI_RETIREMENT: FAIL ({exc})")
    else:
        print("ISSUE74_75_CLI_RETIREMENT: PASS commands=25 scripts_refs=0")

    # #76: current integrated static safety net. No qpx-opt/P3 execution is permitted here.
    try:
        census_proc = _run([sys.executable, str(CENSUS_PATH)])
        assert census_proc.returncode == 0, census_proc.stdout[-4000:]
        selftest_proc = _run([sys.executable, str(BIN_QPX), "self-test"])
        assert selftest_proc.returncode == 0, selftest_proc.stdout[-8000:]
        assert "QPX_HARNESS_SELFTEST: PASS" in selftest_proc.stdout
    except Exception as exc:
        failures.append(f"Issue76 integrated safety net: {exc}")
        print(f"ISSUE76_INTEGRATION: FAIL ({exc})")
    else:
        print("ISSUE76_INTEGRATION: PASS")

    print("ISSUE66_76_SCIENTIFIC_RUNTIME_P3_EVR: NOT_RUN")
    print("ISSUE66_76_EXTERNAL_VALIDATION_ROUND: 1")
    if failures:
        for failure in failures:
            print(f"ISSUE66_76_ERROR: {failure}")
        print("ISSUE66_76_FINAL_GUARD: FAIL")
        return 1
    print("ISSUE66_76_FINAL_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
