"""Performance-specific cache-feasibility interpretation for QPX functors."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from ...cpp.functor_usage import (
    FunctorInspectionError,
    extract_functor_property_declaration,
    parameter_functor_calls,
)
from ...evidence import sha256_file

MATERIAL_RELATIVE = Path("src/materials/QPXThermalDiffusionMaterial.C")
CACHE_ELIGIBLE_SPACE_ARGS = {"ElemQpArg", "ElemSideQpArg"}
CACHE_INELIGIBLE_SPACE_ARGS = {"ElemArg", "FaceArg"}
TARGET_CONSUMER_TYPE = "QPXFVMixtureAveragedDiffusion"
TARGET_PARAMETER = "diffusivity"


class CacheAuditError(RuntimeError):
    pass


def _extract_dmix_declaration(text: str) -> dict[str, Any]:
    try:
        declaration = extract_functor_property_declaration(text, "_D_mix_names")
    except FunctorInspectionError as exc:
        raise CacheAuditError(str(exc)) from exc
    flags = declaration.pop("execution_tokens")
    kind = "DEFAULT_ALWAYS_EVALUATE"
    if flags:
        if "EXEC_ALWAYS" in flags:
            kind = "EXPLICIT_ALWAYS_EVALUATE"
        elif {"EXEC_LINEAR", "EXEC_NONLINEAR"}.issubset(flags):
            kind = "EXPLICIT_LINEAR_NONLINEAR_CLEARANCE"
        else:
            kind = "EXPLICIT_OTHER_CLEARANCE"
    declaration["schedule_kind"] = kind
    declaration["schedule_tokens"] = flags
    declaration["calls_full_evaluate"] = bool(
        declaration["calls_full_evaluate"] and ".D_mix" in declaration["snippet"]
    )
    return declaration


def _parse_input_consumers(input_path: Path) -> list[dict[str, Any]]:
    if not input_path.is_file():
        raise CacheAuditError(f"missing case input: {input_path}")
    text = input_path.read_text(errors="replace")
    rows = []
    current = None
    start_line = 0
    fields = {}
    section_names = {
        "Mesh",
        "Materials",
        "Problem",
        "GlobalParams",
        "UserObjects",
        "Variables",
        "Functions",
        "ICs",
        "FunctorMaterials",
        "FVKernels",
        "Kernels",
        "FVBCs",
        "BCs",
        "Executioner",
        "Postprocessors",
        "AuxVariables",
        "AuxKernels",
        "Outputs",
        "Preconditioning",
        "Adaptivity",
    }

    def flush() -> None:
        nonlocal rows, current, fields
        if current and fields.get("type") == TARGET_CONSUMER_TYPE:
            diffusivity = fields.get(TARGET_PARAMETER, "")
            if diffusivity.startswith("D_mix_"):
                rows.append(
                    {
                        "block": current,
                        "line": start_line,
                        "type": TARGET_CONSUMER_TYPE,
                        "parameter": TARGET_PARAMETER,
                        "functor": diffusivity,
                    }
                )

    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            token = line[1:-1].strip()
            if token == "":
                flush()
                current = None
                fields = {}
            elif not token.startswith("./") and token not in section_names:
                flush()
                current = token
                start_line = lineno
                fields = {}
            continue
        if current and "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip().strip("'\"")
    flush()
    if not rows:
        raise CacheAuditError(
            f"no {TARGET_CONSUMER_TYPE} blocks using D_mix_* through "
            f"'{TARGET_PARAMETER}' found in {input_path}"
        )
    return rows


def audit_qpx_tree(qpx_root: Path, input_path: Path) -> dict[str, Any]:
    root = qpx_root.resolve()
    material = root / MATERIAL_RELATIVE
    if not material.is_file():
        raise CacheAuditError(f"missing material source: {material}")
    declaration = _extract_dmix_declaration(material.read_text(errors="replace"))
    input_consumers = _parse_input_consumers(input_path)
    consumer_types = sorted({row["type"] for row in input_consumers})
    consumers = []
    class_files = {}
    for class_name in consumer_types:
        rows, files = parameter_functor_calls(root, class_name, TARGET_PARAMETER)
        for row in rows:
            row["cache_eligible"] = row["space_arg"] in CACHE_ELIGIBLE_SPACE_ARGS
        consumers.extend(rows)
        class_files[class_name] = files
    counts = {}
    for row in consumers:
        counts[row["space_arg"]] = counts.get(row["space_arg"], 0) + 1

    if not consumers:
        status = "INCONCLUSIVE"
        recommendation = "INCONCLUSIVE"
        reason = (
            "input provenance reached QPXFVMixtureAveragedDiffusion::diffusivity "
            "but the local implementation's functor call argument could not be traced"
        )
        eligible = None
    elif any(row["space_arg"] in CACHE_INELIGIBLE_SPACE_ARGS for row in consumers):
        status = "PASS"
        recommendation = "MATERIAL_SHARED_RESULT_REQUIRED"
        reason = (
            "at least one actual diffusivity consumer uses ElemArg/FaceArg, outside "
            "the native quadrature-point functor cache path"
        )
        eligible = False
    elif any(row["space_arg"] == "UNKNOWN" for row in consumers):
        status = "INCONCLUSIVE"
        recommendation = "INCONCLUSIVE"
        reason = (
            "the input-to-consumer path was resolved, but one or more actual diffusivity "
            "spatial arguments could not be classified without guessing"
        )
        eligible = None
    else:
        eligible = True
        status = "PASS"
        if declaration["schedule_kind"] == "EXPLICIT_LINEAR_NONLINEAR_CLEARANCE":
            recommendation = "NATIVE_CACHE_ALREADY_CONFIGURED"
            reason = (
                "all observed actual diffusivity consumers use quadrature-point arguments "
                "and LINEAR/NONLINEAR clearance is already configured"
            )
        else:
            recommendation = "NATIVE_FUNCTOR_CACHE_CANDIDATE"
            reason = (
                "all observed actual diffusivity consumers use ElemQpArg/ElemSideQpArg "
                "and expected LINEAR/NONLINEAR clearance is not configured"
            )

    return {
        "schema_version": 2,
        "analysis_status": status,
        "qpx_root": str(root),
        "input_path": str(input_path),
        "input_sha256": sha256_file(input_path),
        "material_source": str(material),
        "material_sha256": sha256_file(material),
        "dmix_declaration": declaration,
        "input_consumers": input_consumers,
        "consumer_class_files": class_files,
        "consumers": consumers,
        "space_arg_counts": counts,
        "native_cache_eligible": eligible,
        "recommendation": recommendation,
        "reason": reason,
        "framework_contract": {
            "default_functor_behavior": "always evaluate unless cache clearance is configured",
            "native_qp_cache_space_args": sorted(CACHE_ELIGIBLE_SPACE_ARGS),
            "non_qp_space_args_not_claimed_cacheable": sorted(CACHE_INELIGIBLE_SPACE_ARGS),
            "ad_correctness_guard": (
                "candidate native cache must clear at LINEAR and NONLINEAR before production promotion"
            ),
        },
        "runtime_executed": False,
        "production_source_mutated": False,
    }


def _synthetic_material(schedule=""):
    extra = f", {schedule}" if schedule else ""
    return f'''#include "QPXThermalDiffusionMaterial.h"\nQPXThermalDiffusionMaterial::QPXThermalDiffusionMaterial()\n{{\n  addFunctorProperty<ADReal>(_D_mix_names[i], [this, i](const auto & r, const auto & state) {{ return evaluate(r, state).D_mix[i]; }}{extra});\n}}\n'''


def _synthetic_input():
    return '''[FVKernels]\n  [O2s_diffusion]\n    type = QPXFVMixtureAveragedDiffusion\n    variable = w_O2s\n    diffusivity = D_mix_O2s\n  []\n  [O_diffusion]\n    type = QPXFVMixtureAveragedDiffusion\n    variable = w_O\n    diffusivity = D_mix_O\n  []\n[]\n'''


def _write_tree(root: Path, consumer: str, schedule=""):
    material = root / MATERIAL_RELATIVE
    material.parent.mkdir(parents=True, exist_ok=True)
    material.write_text(_synthetic_material(schedule))
    kernel = root / "src/fvkernels/QPXFVMixtureAveragedDiffusion.C"
    kernel.parent.mkdir(parents=True, exist_ok=True)
    kernel.write_text(consumer)
    input_path = root / "case.i"
    input_path.write_text(_synthetic_input())
    return input_path


def self_test():
    try:
        cases = [
            (
                '''QPXFVMixtureAveragedDiffusion::QPXFVMixtureAveragedDiffusion() : _diffusivity(getFunctor<ADReal>("diffusivity")) {}\nvoid QPXFVMixtureAveragedDiffusion::f(){ const auto qp_arg = makeElemQpArg(_qp); auto v = _diffusivity(qp_arg, determineState()); }''',
                "",
                "NATIVE_FUNCTOR_CACHE_CANDIDATE",
                {"ElemQpArg": 1},
            ),
            (
                '''QPXFVMixtureAveragedDiffusion::QPXFVMixtureAveragedDiffusion() : _diffusivity(getFunctor<ADReal>("diffusivity")) {}\nvoid QPXFVMixtureAveragedDiffusion::f(){ const auto face = makeFace(*_face_info, limiter, true); auto v = _diffusivity(face, determineState()); }''',
                "",
                "MATERIAL_SHARED_RESULT_REQUIRED",
                {"FaceArg": 1},
            ),
            (
                '''QPXFVMixtureAveragedDiffusion::QPXFVMixtureAveragedDiffusion() : _diffusivity(getFunctor<ADReal>("diffusivity")) {}\nvoid QPXFVMixtureAveragedDiffusion::f(){ auto v = _diffusivity(location, determineState()); }''',
                "",
                "INCONCLUSIVE",
                {"UNKNOWN": 1},
            ),
            (
                '''QPXFVMixtureAveragedDiffusion::QPXFVMixtureAveragedDiffusion() : _diffusivity(getFunctor<ADReal>("diffusivity")) {}\nvoid QPXFVMixtureAveragedDiffusion::f(){ Moose::ElemSideQpArg side_qp; auto v = _diffusivity(side_qp, determineState()); }''',
                "{EXEC_LINEAR, EXEC_NONLINEAR}",
                "NATIVE_CACHE_ALREADY_CONFIGURED",
                {"ElemSideQpArg": 1},
            ),
        ]
        for consumer, schedule, recommendation, counts in cases:
            with tempfile.TemporaryDirectory() as tmp_name:
                root = Path(tmp_name)
                input_path = _write_tree(root, consumer, schedule)
                result = audit_qpx_tree(root, input_path)
                assert result["recommendation"] == recommendation, (result, recommendation)
                assert result["space_arg_counts"] == counts, (result, counts)
                assert len(result["input_consumers"]) == 2
                assert result["dmix_declaration"]["calls_full_evaluate"] is True
        print("QPX_CACHE_AUDIT_SELFTEST: PASS")
        return 0
    except Exception as exc:
        print(f"QPX_CACHE_AUDIT_SELFTEST: FAIL: {exc}")
        return 1


__all__ = [
    "CACHE_ELIGIBLE_SPACE_ARGS",
    "CACHE_INELIGIBLE_SPACE_ARGS",
    "MATERIAL_RELATIVE",
    "TARGET_CONSUMER_TYPE",
    "TARGET_PARAMETER",
    "CacheAuditError",
    "audit_qpx_tree",
    "self_test",
]
