"""Synthetic characterization for D_mix equivalence semantics."""
from __future__ import annotations

import math

from ..cpp.calls import self_test as cpp_calls_self_test
from ..cpp.source import self_test as cpp_source_self_test
from .analysis import REL_TOL, TAGS, SPECIES, compare, quoted_values, trace_input
from .source_transform import EquivalenceError, legacy_source, legacy_source_transform


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
        if meta["parser"] != "CppSource+CppCallArguments":
            raise AssertionError("structured call parser was not used")
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

        ambiguous = source.replace(
            "void f()",
            "void g(){ addFunctorProperty<ADReal>(_D_mix_names[i], []{ return evaluateDmix(i,1,2,3,4,5); }); }\nvoid f()",
        )
        try:
            legacy_source(ambiguous)
        except EquivalenceError:
            pass
        else:
            raise AssertionError("ambiguous D_mix producer mutation was not rejected")

        text = (
            "prop_names = 'T p Te neA neB w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'\n"
            "prop_values = '1 2 3 4 5 0.70 0.05 0.01 0.10 0.01 0.01 0.12'\n"
        )
        _, vals = quoted_values(trace_input(text), "prop_values")
        if not any(math.isclose(float(v), 0.99994, abs_tol=1e-14) for v in vals):
            raise AssertionError("trace transform positive control failed")

        baseline = {
            f"Dmix_{tag}_{species}": float(i + 1)
            for i, (tag, species) in enumerate(
                (tag, species) for tag in TAGS for species in SPECIES
            )
        }
        if compare(baseline, dict(baseline), REL_TOL)["status"] != "PASS":
            raise AssertionError("checker positive control failed")
        mutated = dict(baseline)
        mutated["Dmix_B_Op"] *= 1.1
        if compare(baseline, mutated, REL_TOL)["status"] != "FAIL":
            raise AssertionError("checker mutation was not rejected")
    except Exception as exc:
        print(f"DMIX_EQ_SELFTEST: FAIL ({exc})")
        return 1
    print("DMIX_EQ_SELFTEST: PASS")
    return 0
