#!/usr/bin/env python3
"""P0 characterization for cache-audit generic primitive cutovers."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.evidence import artifacts
from qpx_harness import evidence
from qpx_harness.analysis.performance import cache
from qpx_harness.cli.commands import performance as performance_cli
from qpx_harness.cpp import calls as cpp_calls
from qpx_harness.cpp import functor_usage
from qpx_harness.cpp import source as cpp_source


def _fixture() -> str:
    return r'''
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
'''


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
    actual = cache._extract_dmix_declaration(text)
    expected = _expected_declaration(text)
    if actual != expected:
        raise AssertionError(f"D_mix declaration contract drift: {actual!r} != {expected!r}")

    duplicate = text + "\n" + text
    try:
        cache._extract_dmix_declaration(duplicate)
    except cache.CacheAuditError:
        pass
    else:
        raise AssertionError("duplicate-declaration negative control passed")


def _check_run_root_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        results = Path(tmp_name)
        first = performance_cli._cache_run_root(
            results, timestamp="20260831T103000Z"
        )
        second = performance_cli._cache_run_root(
            results, timestamp="20260831T103000Z"
        )
        if first.name != "cache_audit_20260831T103000Z":
            raise AssertionError(f"cache-audit first root naming drift: {first.name}")
        if second.name != "cache_audit_20260831T103000Z_01":
            raise AssertionError(f"cache-audit collision naming drift: {second.name}")
        if not first.is_dir() or not second.is_dir():
            raise AssertionError("cache-audit run roots were not created")


def _check_production_cutover() -> None:
    analysis_source = Path(cache.__file__).read_text()
    cpp_source_text = Path(functor_usage.__file__).read_text()
    cli_source = Path(performance_cli.__file__).read_text()
    for required in (
        "extract_functor_property_declaration",
        "parameter_functor_calls",
        '"input_sha256": sha256_file(input_path)',
        '"material_sha256": sha256_file(material)',
    ):
        if required not in analysis_source:
            raise AssertionError(f"cache analysis cutover missing: {required}")

    for required in (
        'cpp.calls("addFunctorProperty", containing=property_marker)',
        "split_call_arguments(cpp, call)",
        "masked = CppSource(text).masked",
        "def parameter_functor_calls(",
    ):
        if required not in cpp_source_text:
            raise AssertionError(f"C++ functor inspection cutover missing: {required}")

    for required in (
        'argparse.ArgumentParser(prog="qpx cache-audit")',
        "create_collision_safe_directory",
        "write_json_bundle(",
        "cache.audit_qpx_tree(",
    ):
        if required not in cli_source:
            raise AssertionError(f"cache CLI cutover missing: {required}")

    for forbidden in (
        "def _mask_cpp(",
        "def _matching_paren(",
        "def _split_top_level_args(",
        "def _sha256_file(",
        "import hashlib",
        "from datetime import datetime, timezone",
        "datetime.now(timezone.utc)",
        "summary.write_text(json.dumps(result",
    ):
        if forbidden in analysis_source or forbidden in cpp_source_text:
            raise AssertionError(f"cache-audit retained duplicated infrastructure: {forbidden}")

    # Cache-feasibility interpretation remains caller-owned at this checkpoint.
    for retained in (
        "NATIVE_FUNCTOR_CACHE_CANDIDATE",
        "MATERIAL_SHARED_RESULT_REQUIRED",
        "NATIVE_CACHE_ALREADY_CONFIGURED",
        '"runtime_executed": False',
        '"production_source_mutated": False',
    ):
        if retained not in analysis_source:
            raise AssertionError(f"cache-audit policy moved prematurely: {retained}")

    for forbidden in ("argparse", "write_json_bundle", "utc_timestamp"):
        if forbidden in analysis_source:
            raise AssertionError(f"cache analysis retained CLI presentation: {forbidden}")


def _check_primitive_boundary() -> None:
    for module in (cpp_source, cpp_calls, functor_usage, evidence, artifacts):
        source = Path(module.__file__).read_text()
        for forbidden in (
            "QPXFVMixtureAveragedDiffusion",
            "NATIVE_FUNCTOR_CACHE_CANDIDATE",
            "MATERIAL_SHARED_RESULT_REQUIRED",
        ):
            if forbidden in source:
                raise AssertionError(
                    f"generic primitive leaked cache-audit policy: {forbidden}"
                )


def main() -> int:
    try:
        if cpp_source.self_test() != 0:
            raise AssertionError("CppSource self-test failed")
        if cpp_calls.self_test() != 0:
            raise AssertionError("CppCall self-test failed")
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
