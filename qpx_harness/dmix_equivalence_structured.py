"""Structured D_mix equivalence adapter using reusable C++ call parsing."""

from __future__ import annotations

import math
import sys
from typing import Iterable

from . import dmix_equivalence as base
from .cpp_calls import CppCallError, self_test as cpp_calls_self_test, split_call_arguments
from .cpp_source import CppSource, CppSourceError, self_test as cpp_source_self_test


EquivalenceError = base.EquivalenceError


def legacy_source_transform(source: str):
    """Reconstruct legacy full evaluate(...) from the actual evaluateDmix(...) arguments.

    Production optimized contract:

        return evaluateDmix(species_i, T, p, Te, ne, Y);

    Legacy contract:

        return evaluate(T, p, Te, ne, Y).D_mix[species_i];

    Argument expressions are preserved structurally rather than hardcoded, so
    functor/state expressions can change without breaking the validator.
    """
    try:
        cpp = CppSource(source)
        cpp.require_tokens(
            (
                "QPXThermalDiffusionMaterial::evaluate",
                "QPXThermalDiffusionMaterial::evaluateDmix",
                "_D_mix_names",
            )
        )
        functor_call = cpp.unique_call("addFunctorProperty", containing="_D_mix_names")
        lambda_body = cpp.lambda_body(functor_call)
        dmix_call = cpp.unique_call("evaluateDmix", within=lambda_body)
        parsed = split_call_arguments(cpp, dmix_call)
        return_stmt = cpp.unique_return_call("evaluateDmix", within=lambda_body)
    except (CppSourceError, CppCallError) as exc:
        raise EquivalenceError(f"structural C++ source inspection failed: {exc}") from exc

    args = parsed.arguments
    if len(args) != 6:
        raise EquivalenceError(
            "evaluateDmix production contract expected 6 arguments "
            f"(species_i,T,p,Te,ne,Y), found {len(args)}: {args}"
        )

    species_index = args[0].strip()
    evaluate_args = ", ".join(arg.strip() for arg in args[1:])
    replacement = f"return evaluate({evaluate_args}).D_mix[{species_index}];"
    patched = cpp.replace(return_stmt, replacement)
    if patched == source:
        raise EquivalenceError("legacy source transform produced no change")

    metadata = {
        "parser": "CppSource+CppCallArguments",
        "functor_call_span": [functor_call.start, functor_call.end],
        "lambda_body_span": [lambda_body.start, lambda_body.end],
        "dmix_call_span": [dmix_call.start, dmix_call.end],
        "return_statement_span": [return_stmt.start, return_stmt.end],
        "dmix_arguments": list(args),
        "original_return": return_stmt.slice(source).strip(),
        "replacement_return": replacement,
    }
    return patched, metadata


def legacy_source(source: str) -> str:
    return legacy_source_transform(source)[0]


def self_test() -> int:
    try:
        if cpp_source_self_test():
            raise AssertionError("CppSource self-test failed")
        if cpp_calls_self_test():
            raise AssertionError("CppCallArguments self-test failed")

        source = r'''
void f()
{
  addFunctorProperty<ADReal>(
      _D_mix_names[i],
      [this, i](const auto & r, const auto & state)
      {
        return evaluateDmix(
            i,
            temperature(r, state),
            pressure(foo(1, 2), state),
            Te(r, state),
            ne(r, state),
            composition(bar(3, 4), state));
      });
}
Result QPXThermalDiffusionMaterial::evaluate(int, int, int, int, int) const { return {}; }
ADReal QPXThermalDiffusionMaterial::evaluateDmix(int, int, int, int, int, int) const { return {}; }
'''
        patched, meta = legacy_source_transform(source)
        expected = (
            "return evaluate(temperature(r, state), pressure(foo(1, 2), state), "
            "Te(r, state), ne(r, state), composition(bar(3, 4), state)).D_mix[i];"
        )
        if expected not in patched:
            raise AssertionError(meta)
        if meta["dmix_arguments"][0] != "i":
            raise AssertionError("species index was not preserved")

        wrong_arity = source.replace(
            "composition(bar(3, 4), state)",
            "extra(r, state), composition(bar(3, 4), state)",
        )
        try:
            legacy_source_transform(wrong_arity)
        except EquivalenceError:
            pass
        else:
            raise AssertionError("evaluateDmix arity mutation was not rejected")

        text = (
            "prop_names = 'T p Te neA neB w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'\n"
            "prop_values = '1 2 3 4 5 0.70 0.05 0.01 0.10 0.01 0.01 0.12'\n"
        )
        _, values = base.quoted_values(base.trace_input(text), "prop_values")
        if not any(math.isclose(float(v), 0.99994, abs_tol=1e-14) for v in values):
            raise AssertionError("trace transform control failed")

        baseline = {
            f"Dmix_{tag}_{species}": float(i + 1)
            for i, (tag, species) in enumerate(
                (tag, species) for tag in base.TAGS for species in base.SPECIES
            )
        }
        if base.compare(baseline, dict(baseline), base.REL_TOL)["status"] != "PASS":
            raise AssertionError("comparison positive control failed")
        mutated = dict(baseline)
        mutated["Dmix_B_Op"] *= 1.1
        if base.compare(baseline, mutated, base.REL_TOL)["status"] != "FAIL":
            raise AssertionError("comparison mutation was not rejected")
    except Exception as exc:
        print(f"DMIX_EQ_STRUCTURED_SELFTEST: FAIL ({exc})")
        return 1
    print("DMIX_EQ_STRUCTURED_SELFTEST: PASS")
    return 0


def _activate() -> None:
    base.legacy_source_transform = legacy_source_transform
    base.legacy_source = legacy_source
    base.self_test = self_test


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv) if argv is not None else list(sys.argv[1:])
    _activate()
    if "--self-test" in args:
        return self_test()
    return base.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
