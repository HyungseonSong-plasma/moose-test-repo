"""Input-aware static cache-feasibility audit for QPXThermalDiffusionMaterial D_mix functors."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .cpp_calls import split_call_arguments
from .cpp_source import CppSource, CppSourceError

MATERIAL_RELATIVE = Path("src/materials/QPXThermalDiffusionMaterial.C")
DEFAULT_CASE_RELATIVE = Path("tests/Issue22_qvt_transient_species_accumulation/input.i")
TEXT_SUFFIXES = {".C", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp"}
CACHE_ELIGIBLE_SPACE_ARGS = {"ElemQpArg", "ElemSideQpArg"}
CACHE_INELIGIBLE_SPACE_ARGS = {"ElemArg", "FaceArg"}
TARGET_CONSUMER_TYPE = "QPXFVMixtureAveragedDiffusion"
TARGET_PARAMETER = "diffusivity"


class CacheAuditError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _extract_dmix_declaration(text: str) -> dict[str, Any]:
    cpp = CppSource(text)
    calls = [
        call
        for call in cpp.calls("addFunctorProperty", containing="_D_mix_names")
        if re.search(r"addFunctorProperty\s*<\s*ADReal\s*>", call.slice(text))
    ]
    if len(calls) != 1:
        raise CacheAuditError(
            f"expected exactly one D_mix addFunctorProperty declaration, found {len(calls)}"
        )

    call = calls[0]
    raw = call.slice(text)
    args = split_call_arguments(cpp, call).arguments
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
        "line": _line_number(text, call.start),
        "argument_count": len(args),
        "schedule_kind": kind,
        "schedule_tokens": flags,
        "calls_full_evaluate": "evaluate" in raw and ".D_mix" in raw,
        "snippet": " ".join(raw.split())[:700],
    }


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


def _source_files(root: Path) -> list[Path]:
    out = []
    for base_name in ("src", "include"):
        base = root / base_name
        if base.is_dir():
            out += [
                path
                for path in base.rglob("*")
                if path.is_file() and path.suffix in TEXT_SUFFIXES
            ]
    return sorted(out)


def _class_files(root: Path, class_name: str) -> list[Path]:
    files = []
    for path in _source_files(root):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if class_name in text:
            files.append(path)
    return files


def _space_arg_bindings(text: str) -> dict[str, str]:
    masked = CppSource(text).masked
    out = {}
    patterns = {
        "ElemQpArg": [
            r"\b(?:const\s+)?auto(?:\s*&)?\s+([A-Za-z_]\w*)\s*=\s*makeElemQpArg\s*\(",
            r"\b(?:Moose::)?ElemQpArg\s+([A-Za-z_]\w*)",
        ],
        "ElemSideQpArg": [
            r"\b(?:const\s+)?auto(?:\s*&)?\s+([A-Za-z_]\w*)\s*=\s*makeElemSideQpArg\s*\(",
            r"\b(?:Moose::)?ElemSideQpArg\s+([A-Za-z_]\w*)",
        ],
        "ElemArg": [
            r"\b(?:const\s+)?auto(?:\s*&)?\s+([A-Za-z_]\w*)\s*=\s*makeElemArg\s*\(",
            r"\b(?:Moose::)?ElemArg\s+([A-Za-z_]\w*)",
        ],
        "FaceArg": [
            r"\b(?:const\s+)?auto(?:\s*&)?\s+([A-Za-z_]\w*)\s*=\s*(?:makeFace|makeFaceArg)\s*\(",
            r"\b(?:Moose::)?FaceArg\s+([A-Za-z_]\w*)",
        ],
    }
    for kind, expressions in patterns.items():
        for expression in expressions:
            for match in re.finditer(expression, masked):
                out[match.group(1)] = kind
    return out


def _infer_space_arg(expr: str, bindings: dict[str, str]) -> str:
    stripped = expr.strip()
    for kind, tokens in [
        ("ElemSideQpArg", ("makeElemSideQpArg", "ElemSideQpArg")),
        ("ElemQpArg", ("makeElemQpArg", "ElemQpArg")),
        ("FaceArg", ("makeFaceArg", "makeFace", "FaceArg")),
        ("ElemArg", ("makeElemArg", "ElemArg")),
    ]:
        if any(token in stripped for token in tokens):
            return kind
    if re.fullmatch(r"[A-Za-z_]\w*", stripped) and stripped in bindings:
        return bindings[stripped]
    return "UNKNOWN"


def _parameter_functor_variables(text: str, parameter: str) -> set[str]:
    out = set()
    patterns = [
        rf"\b([A-Za-z_]\w*)\s*\(\s*getFunctor\s*<\s*ADReal\s*>\s*\([^)]*[\"']{re.escape(parameter)}[\"'][^)]*\)\s*\)",
        rf"\b([A-Za-z_]\w*)\s*=\s*getFunctor\s*<\s*ADReal\s*>\s*\([^;]*[\"']{re.escape(parameter)}[\"'][^;]*\)",
        rf"\b([A-Za-z_]\w*)\s*\(\s*getFunctor\s*<\s*ADReal\s*>\s*\([^)]*getParam[^)]*[\"']{re.escape(parameter)}[\"']",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.S):
            out.add(match.group(1))
    if re.search(rf"[\"']{re.escape(parameter)}[\"']", text):
        for name in (f"_{parameter}", parameter):
            if re.search(rf"\b{re.escape(name)}\b", text):
                out.add(name)
    return out


def _consumer_calls_for_parameter(root: Path, class_name: str, parameter: str):
    files = _class_files(root, class_name)
    if not files:
        return [], []
    texts = {}
    combined = ""
    for path in files:
        text = path.read_text(errors="replace")
        texts[path] = text
        combined += "\n" + text
    variables = _parameter_functor_variables(combined, parameter)
    rows = []
    for path, text in texts.items():
        cpp = CppSource(text)
        bindings = _space_arg_bindings(text)
        for variable in sorted(variables, key=len, reverse=True):
            for call in cpp.calls(variable):
                try:
                    parsed = split_call_arguments(cpp, call)
                except CppSourceError:
                    continue
                if not parsed.arguments:
                    continue
                first = parsed.arguments[0]
                if "getFunctor" in first:
                    continue
                kind = _infer_space_arg(first, bindings)
                line_start = text.rfind("\n", 0, call.start) + 1
                line_end = text.find("\n", parsed.close_paren)
                line_end = len(text) if line_end < 0 else line_end
                rows.append(
                    {
                        "path": str(path.relative_to(root)),
                        "line": _line_number(text, call.start),
                        "consumer_type": class_name,
                        "parameter": parameter,
                        "functor_variable": variable,
                        "first_argument": first.strip()[:240],
                        "space_arg": kind,
                        "cache_eligible": kind in CACHE_ELIGIBLE_SPACE_ARGS,
                        "snippet": " ".join(text[line_start:line_end].split())[:700],
                    }
                )
    unique = {}
    for row in rows:
        unique[
            (
                row["path"],
                row["line"],
                row["functor_variable"],
                row["first_argument"],
            )
        ] = row
    return list(unique.values()), [str(path.relative_to(root)) for path in files]


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
        rows, files = _consumer_calls_for_parameter(root, class_name, TARGET_PARAMETER)
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
        "input_sha256": _sha256_file(input_path),
        "material_source": str(material),
        "material_sha256": _sha256_file(material),
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


def _new_run_root(results: Path):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = results / f"cache_audit_{stamp}"
    candidate = base
    index = 1
    while candidate.exists():
        candidate = Path(f"{base}_{index:02d}")
        index += 1
    candidate.mkdir(parents=True)
    return candidate


def main(argv: Iterable[str] | None = None):
    parser = argparse.ArgumentParser(prog="qpx cache-audit")
    parser.add_argument("--qpx")
    parser.add_argument("--input")
    parser.add_argument("--results-root")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.self_test:
        return self_test()
    if not args.qpx:
        parser.error("--qpx is required unless --self-test is used")
    qpx = Path(args.qpx).expanduser().resolve()
    if not qpx.is_file():
        print(f"QPX_CACHE_AUDIT_ERROR: qpx executable not found: {qpx}", file=sys.stderr)
        return 2
    repo_root = Path(__file__).resolve().parents[1]
    input_path = (
        Path(args.input).expanduser().resolve()
        if args.input
        else repo_root / DEFAULT_CASE_RELATIVE
    )
    try:
        result = audit_qpx_tree(qpx.parent, input_path)
        results = (
            Path(args.results_root).expanduser().resolve()
            if args.results_root
            else qpx.parent / "temp" / "results"
        )
        root = _new_run_root(results)
        result["qpx_executable"] = str(qpx)
        summary = root / "cache_audit.json"
        summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    except Exception as exc:
        print(f"QPX_CACHE_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 2

    type_counts = {}
    for row in result["input_consumers"]:
        type_counts[row["type"]] = type_counts.get(row["type"], 0) + 1
    print(f"QPX_CACHE_AUDIT_ROOT: {root}")
    print(f"QPX_CACHE_AUDIT_STATUS: {result['analysis_status']}")
    print(f"QPX_CACHE_INPUT: {result['input_path']}")
    print("QPX_CACHE_INPUT_CONSUMERS:", json.dumps(type_counts, sort_keys=True))
    print(f"QPX_CACHE_MATERIAL_SHA256: {result['material_sha256']}")
    print(f"QPX_CACHE_DMIX_DECLARATION: {result['dmix_declaration']['schedule_kind']}")
    print("QPX_CACHE_DMIX_CALLS_FULL_EVALUATE:", result["dmix_declaration"]["calls_full_evaluate"])
    print("QPX_CACHE_SPACE_ARGS:", json.dumps(result["space_arg_counts"], sort_keys=True))
    print(f"QPX_CACHE_NATIVE_ELIGIBLE: {result['native_cache_eligible']}")
    print(f"QPX_CACHE_RECOMMENDATION: {result['recommendation']}")
    print(f"QPX_CACHE_REASON: {result['reason']}")
    print(f"QPX_CACHE_SUMMARY: {summary}")
    return 0 if result["analysis_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
