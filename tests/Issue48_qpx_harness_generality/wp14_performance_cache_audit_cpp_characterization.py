#!/usr/bin/env python3
"""P0 characterization for cache-audit generic C++ primitive cutover."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import cpp_calls
from qpx_harness import cpp_source
from qpx_harness import performance_cache_audit as cache


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


def _check_production_cutover() -> None:
    source = Path(cache.__file__).read_text()
    for required in (
        "from .cpp_calls import split_call_arguments",
        "from .cpp_source import CppSource",
        'cpp.calls("addFunctorProperty", containing="_D_mix_names")',
        "split_call_arguments(cpp, call)",
        "masked = CppSource(text).masked",
    ):
        if required not in source:
            raise AssertionError(f"cache-audit generic C++ cutover missing: {required}")

    for forbidden in (
        "def _mask_cpp(",
        "def _matching_paren(",
        "def _split_top_level_args(",
    ):
        if forbidden in source:
            raise AssertionError(f"cache-audit retained duplicated lexical helper: {forbidden}")

    # This checkpoint is intentionally limited to C++ parsing ownership.
    for retained in (
        "def _sha256_file(",
        "datetime.now(timezone.utc)",
        "json.dumps(result, indent=2, sort_keys=True)",
        "NATIVE_FUNCTOR_CACHE_CANDIDATE",
        "MATERIAL_SHARED_RESULT_REQUIRED",
    ):
        if retained not in source:
            raise AssertionError(f"cache-audit ownership moved prematurely: {retained}")


def _check_primitive_boundary() -> None:
    for module in (cpp_source, cpp_calls):
        source = Path(module.__file__).read_text()
        for forbidden in (
            "performance_cache_audit",
            "QPXFVMixtureAveragedDiffusion",
            "NATIVE_FUNCTOR_CACHE_CANDIDATE",
        ):
            if forbidden in source:
                raise AssertionError(
                    f"generic C++ primitive leaked cache-audit policy: {forbidden}"
                )


def main() -> int:
    try:
        if cpp_source.self_test() != 0:
            raise AssertionError("CppSource self-test failed")
        if cpp_calls.self_test() != 0:
            raise AssertionError("CppCall self-test failed")
        _check_declaration_contract()
        _check_production_cutover()
        _check_primitive_boundary()
    except Exception as exc:
        print(f"ISSUE48_CACHE_AUDIT_CPP_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_CACHE_AUDIT_CPP_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
