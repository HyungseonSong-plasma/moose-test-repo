#!/usr/bin/env python3
"""P0 characterization for the historical cache-audit primitive contracts."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics_harness import evidence
from physics_harness.adapters.moose import source_inspection as moose_observation
from physics_harness.application import performance as performance_application
from physics_harness.cli.commands import performance as performance_cli
from physics_harness.evidence import artifacts
from physics_harness.observation.source_code import cpp as cpp_observation


# Historical cache-audit policy oracle preserved from Git blob
# 38e4aa90e67829b536cdf690c7a32596c282ae95; reusable mechanics are
# resolved through current physics_harness owners.
class HistoricalCacheAuditError(RuntimeError):
    """Compatibility error for the retired cache-audit characterization oracle."""


def _historical_dmix_declaration(text: str) -> dict:
    """Preserve the retired cache-audit declaration contract on current primitives."""
    try:
        structural = moose_observation.extract_functor_property_declaration(
            text,
            "_D_mix_names",
        )
    except moose_observation.FunctorInspectionError as exc:
        raise HistoricalCacheAuditError(str(exc)) from exc

    flags = list(structural["execution_tokens"])
    kind = "DEFAULT_ALWAYS_EVALUATE"
    if flags:
        if "EXEC_ALWAYS" in flags:
            kind = "EXPLICIT_ALWAYS_EVALUATE"
        elif {"EXEC_LINEAR", "EXEC_NONLINEAR"}.issubset(flags):
            kind = "EXPLICIT_LINEAR_NONLINEAR_CLEARANCE"
        else:
            kind = "EXPLICIT_OTHER_CLEARANCE"
    return {
        "line": structural["line"],
        "argument_count": structural["argument_count"],
        "schedule_kind": kind,
        "schedule_tokens": flags,
        "calls_full_evaluate": bool(
            structural["calls_full_evaluate"] and ".D_mix" in structural["snippet"]
        ),
        "snippet": structural["snippet"],
    }


def _historical_cache_run_root(results: Path, *, timestamp: str) -> Path:
    """Preserve the retired CLI run-root naming contract via canonical evidence."""
    return evidence.create_collision_safe_directory(
        results,
        f"cache_audit_{timestamp}",
    )


def _fixture() -> str:
    return r"""
// fake addFunctorProperty<ADReal>(_D_mix_names[i], ignored);
const char * fake = "addFunctorProperty<ADReal>(_D_mix_names[i], ignored)";
QPXThermalDiffusionMaterial::QPXThermalDiffusionMaterial()
{
  addFunctorProperty<ADReal>(
      _D_mix_names[i],
      [this, i](const auto & r, const auto & state)
      {
        return evaluate(r, state).D_mix[i];
      },
      {EXEC_LINEAR, EXEC_NONLINEAR});
}
"""


def _expected_declaration(text: str) -> dict:
    snippet = " ".join(
        """addFunctorProperty<ADReal>(
      _D_mix_names[i],
      [this, i](const auto & r, const auto & state)
      {
        return evaluate(r, state).D_mix[i];
      },
      {EXEC_LINEAR, EXEC_NONLINEAR})""".split()
    )
    return {
        "line": 6,
        "argument_count": 3,
        "schedule_kind": "EXPLICIT_LINEAR_NONLINEAR_CLEARANCE",
        "schedule_tokens": ["EXEC_LINEAR", "EXEC_NONLINEAR"],
        "calls_full_evaluate": True,
        "snippet": snippet[:700],
    }


def _check_declaration_contract() -> None:
    text = _fixture()
    actual = _historical_dmix_declaration(text)
    expected = _expected_declaration(text)
    if actual != expected:
        raise AssertionError(f"D_mix declaration contract drift: {actual!r} != {expected!r}")

    duplicate = text + "\n" + text
    try:
        _historical_dmix_declaration(duplicate)
    except HistoricalCacheAuditError:
        pass
    else:
        raise AssertionError("duplicate-declaration negative control passed")


def _check_run_root_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        results = Path(tmp_name)
        first = _historical_cache_run_root(
            results, timestamp="20260831T103000Z"
        )
        second = _historical_cache_run_root(
            results, timestamp="20260831T103000Z"
        )
        if first.name != "cache_audit_20260831T103000Z":
            raise AssertionError(f"cache-audit first root naming drift: {first.name}")
        if second.name != "cache_audit_20260831T103000Z_01":
            raise AssertionError(f"cache-audit collision naming drift: {second.name}")
        if not first.is_dir() or not second.is_dir():
            raise AssertionError("cache-audit run roots were not created")


def _check_production_cutover() -> None:
    cpp_source = Path(cpp_observation.__file__).read_text()
    moose_source = Path(moose_observation.__file__).read_text()
    evidence_identity_source = (ROOT / "physics_harness/evidence/identity.py").read_text()
    artifacts_source = Path(artifacts.__file__).read_text()
    application_source = Path(performance_application.__file__).read_text()
    cli_source = Path(performance_cli.__file__).read_text()
    cli_app_source = (ROOT / "physics_harness/cli/app.py").read_text()

    for required in (
        "extract_functor_property_declaration",
        "parameter_functor_calls",
        'cpp.calls("addFunctorProperty", containing=property_marker)',
        "split_call_arguments(cpp, call)",
        "masked = CppSource(text).masked",
        "def parameter_functor_calls(",
    ):
        if required not in moose_source:
            raise AssertionError(f"MOOSE source-inspection cutover missing: {required}")

    for required in (
        "class CppSource:",
        "def split_call_arguments(",
    ):
        if required not in cpp_source:
            raise AssertionError(f"C++ source-observation primitive missing: {required}")

    for required in (
        "def sha256_file(",
        "def create_collision_safe_directory(",
    ):
        if required not in evidence_identity_source:
            raise AssertionError(f"evidence identity primitive missing: {required}")

    if "def write_json_bundle(" not in artifacts_source:
        raise AssertionError("evidence artifact primitive missing: write_json_bundle")

    for required in ("def run_measurement(", "def analyze_profile("):
        if required not in application_source:
            raise AssertionError(f"performance application boundary missing: {required}")
    if "from ...application import performance" not in cli_source:
        raise AssertionError("performance CLI no longer routes through the application boundary")

    retired_cache_analysis = ROOT / "physics_harness/analysis/performance/cache.py"
    if retired_cache_analysis.exists():
        raise AssertionError("retired campaign-specific cache analysis returned to production")
    if '"cache-audit"' in cli_app_source:
        raise AssertionError("retired cache-audit command returned to the generic CLI")

    for forbidden in (
        "def _mask_cpp(",
        "def _matching_paren(",
        "def _split_top_level_args(",
        "def _sha256_file(",
    ):
        if forbidden in moose_source or forbidden in cpp_source:
            raise AssertionError(f"source inspection retained duplicated infrastructure: {forbidden}")


def _check_primitive_boundary() -> None:
    for module in (
        cpp_observation,
        moose_observation,
        evidence,
        artifacts,
        performance_application,
        performance_cli,
    ):
        source = Path(module.__file__).read_text()
        for forbidden in (
            "QPXFVMixtureAveragedDiffusion",
            "NATIVE_FUNCTOR_CACHE_CANDIDATE",
            "MATERIAL_SHARED_RESULT_REQUIRED",
        ):
            if forbidden in source:
                raise AssertionError(
                    f"generic primitive leaked retired cache-audit policy: {forbidden}"
                )


def main() -> int:
    try:
        _check_declaration_contract()
        _check_run_root_contract()
        _check_production_cutover()
        _check_primitive_boundary()
    except Exception as exc:
        print(f"ISSUE48_CACHE_AUDIT_CPP_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_CACHE_AUDIT_CPP_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
