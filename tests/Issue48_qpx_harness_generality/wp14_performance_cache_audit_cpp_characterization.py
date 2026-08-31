#!/usr/bin/env python3
"""P0 characterization for cache-audit migration to generic C++ primitives."""
from __future__ import annotations

import re
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


def _generic_declaration(text: str) -> dict:
    cpp = cpp_source.CppSource(text)
    call = cpp.unique_call("addFunctorProperty", containing="_D_mix_names")
    args = cpp_calls.split_call_arguments(cpp, call).arguments
    raw = call.slice(text)
    flags = sorted(set(re.findall(r"\bEXEC_[A-Z0-9_]+\b", raw)))
    kind = "DEFAULT_ALWAYS_EVALUATE"
    if flags:
        if "EXEC_ALWAYS" in flags:
            kind = "EXPLICIT_ALWAYS_EVALUATE"
        elif {"EXEC_LINEAR", "EXEC_NONLINEAR"}.issubset(flags):
            kind = "EXPLICIT_LINEAR_NONLINEAR_CLEARANCE"
        else:
            kind = "EXPLICIT_OTHER_CLEARANCE"
    return {
        "line": text.count("\n", 0, call.start) + 1,
        "argument_count": len(args),
        "schedule_kind": kind,
        "schedule_tokens": flags,
        "calls_full_evaluate": "evaluate" in raw and ".D_mix" in raw,
        "snippet": " ".join(raw.split())[:700],
    }


def _check_mask_equivalence() -> None:
    text = _fixture()
    if cache._mask_cpp(text) != cpp_source.mask_cpp(text):
        raise AssertionError("cache-audit mask differs from generic C++ mask on accepted syntax")


def _check_balanced_call_equivalence() -> None:
    text = _fixture()
    legacy_masked = cache._mask_cpp(text)
    match = re.search(r"addFunctorProperty\s*<\s*ADReal\s*>\s*\(", legacy_masked)
    if match is None:
        raise AssertionError("fixture addFunctorProperty call not found")
    legacy_open = legacy_masked.find("(", match.start())
    legacy_close = cache._matching_paren(legacy_masked, legacy_open)

    cpp = cpp_source.CppSource(text)
    call = cpp.unique_call("addFunctorProperty", containing="_D_mix_names")
    generic_args = cpp_calls.split_call_arguments(cpp, call)
    if generic_args.open_paren != legacy_open or generic_args.close_paren != legacy_close:
        raise AssertionError("balanced call boundary drift")

    legacy_args = tuple(cache._split_top_level_args(text[legacy_open + 1 : legacy_close]))
    if generic_args.arguments != legacy_args:
        raise AssertionError(
            f"top-level argument split drift: {generic_args.arguments!r} != {legacy_args!r}"
        )


def _check_declaration_equivalence() -> None:
    text = _fixture()
    legacy = cache._extract_dmix_declaration(text)
    generic = _generic_declaration(text)
    if legacy != generic:
        raise AssertionError(f"D_mix declaration contract drift: {legacy!r} != {generic!r}")

    duplicate = text + "\n" + text
    try:
        cache._extract_dmix_declaration(duplicate)
    except cache.CacheAuditError:
        pass
    else:
        raise AssertionError("legacy duplicate-declaration negative control passed")
    try:
        cpp_source.CppSource(duplicate).unique_call(
            "addFunctorProperty", containing="_D_mix_names"
        )
    except cpp_source.CppSourceError:
        pass
    else:
        raise AssertionError("generic duplicate-declaration negative control passed")


def _check_primitive_boundary() -> None:
    for module in (cpp_source, cpp_calls):
        source = Path(module.__file__).read_text()
        for forbidden in (
            "performance_cache_audit",
            "QPXFVMixtureAveragedDiffusion",
            "D_mix_",
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
        _check_mask_equivalence()
        _check_balanced_call_equivalence()
        _check_declaration_equivalence()
        _check_primitive_boundary()
    except Exception as exc:
        print(f"ISSUE48_CACHE_AUDIT_CPP_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_CACHE_AUDIT_CPP_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
