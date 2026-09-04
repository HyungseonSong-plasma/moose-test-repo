"""Structural C++ legacy-source reconstruction for D_mix equivalence."""
from __future__ import annotations

from typing import Any

from ..observation.source_code.cpp import (
    CppCallError,
    CppSource,
    CppSourceError,
    split_call_arguments,
)


class EquivalenceError(RuntimeError):
    pass


def legacy_source_transform(source: str) -> tuple[str, dict[str, Any]]:
    """Reconstruct the legacy full evaluate(...) call from evaluateDmix(...)."""
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
