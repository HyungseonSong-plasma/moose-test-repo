"""Direct-PerfGraph PF-3 transport probe backend.

Own direct PerfGraphRegistry/PerfGuard instrumentation and PF-3 interpretation;
delegate C++ structure, PerfGraph hierarchy, and managed runtime mechanics to
reusable harness primitives.
"""
from __future__ import annotations

import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any

from ...analysis.performance import perfgraph
from ...observation.source_code.cpp import CppSource, CppSourceError, Span

TIMER_NAMES = {
    "evaluate": "qpx_transport_evaluate",
    "collision_pairs": "qpx_transport_collision_pairs",
    "dmix": "qpx_transport_dmix",
    "functor_DT": "qpx_transport_functor_DT",
    "functor_kT": "qpx_transport_functor_kT",
    "functor_Dmix": "qpx_transport_functor_Dmix",
}
MARKER_PREFIX = "qpx_transport_"
PROBE_MACRO = "QPX_TRANSPORT_TIME_SECTION"


class ProbeError(RuntimeError):
    pass


def _timer_call(key: str, level: int) -> str:
    return f'{PROBE_MACRO}({key}, "{TIMER_NAMES[key]}", {level});'


def _timer_after_brace(text: str, brace: int, key: str, level: int) -> tuple[int, str]:
    line_start = text.rfind("\n", 0, brace) + 1
    match = re.match(r"[ \t]*", text[line_start:brace])
    indent = (match.group(0) if match else "") + "  "
    call = _timer_call(key, level)
    payload = f"\n{indent}{call}" if brace + 1 < len(text) and text[brace + 1] == "\n" else f"\n{indent}{call}\n{indent}"
    return brace + 1, payload


def _wrap_for_timer(text: str, span: Span, key: str, level: int) -> list[tuple[int, str]]:
    cpp = CppSource(text)
    close_idx = span.end - 1
    i = span.start - 1
    while i >= 0 and cpp.masked[i].isspace():
        i -= 1
    if i < 0 or cpp.masked[i] != ")":
        raise ProbeError("for-loop instrumentation expected ')' before body")
    try:
        open_paren = cpp.match_backward(i, "(", ")")
    except CppSourceError as exc:
        raise ProbeError(str(exc)) from exc
    j = open_paren - 1
    while j >= 0 and cpp.masked[j].isspace():
        j -= 1
    end = j + 1
    while j >= 0 and (cpp.masked[j].isalnum() or cpp.masked[j] == "_"):
        j -= 1
    if cpp.masked[j + 1 : end] != "for":
        raise ProbeError("instrumentation span is not a for-loop body")
    for_start = j + 1
    line_start = text.rfind("\n", 0, for_start) + 1
    match = re.match(r"[ \t]*", text[line_start:for_start])
    indent = match.group(0) if match else ""
    return [
        (line_start, f"{indent}{{\n{indent}  {_timer_call(key, level)}\n"),
        (close_idx + 1, f"\n{indent}}}"),
    ]


def _support_block() -> str:
    return (
        "\n#ifndef QPX_TRANSPORT_TIME_SECTION\n"
        "#define QPX_TRANSPORT_TIME_SECTION(token, section_name, level)                                  \\\n"
        "  static const PerfID token##_perf_id = []() {                                                  \\\n"
        "    auto & registry = moose::internal::getPerfGraphRegistry();                                  \\\n"
        "    return registry.sectionExists(section_name) ? registry.sectionID(section_name)               \\\n"
        "                                                : registry.registerSection(section_name, level);  \\\n"
        "  }();                                                                                            \\\n"
        "  PerfGuard token##_perf_guard(getMooseApp().perfGraph(), token##_perf_id)\n"
        "#endif\n"
    )


def _has_legacy_time_section(text: str) -> bool:
    return re.search(r"\bTIME_SECTION\s*\(", text) is not None


def instrument_source(text: str) -> tuple[str, dict[str, Any]]:
    """Add source-only PerfGuard instrumentation without changing physics."""
    if MARKER_PREFIX in text or PROBE_MACRO in text:
        raise ProbeError("source already contains qpx transport instrumentation markers")
    mandatory = (
        "QPXThermalDiffusionMaterial::evaluate",
        "_D_T_names",
        "_kT_names",
        "_D_mix_names",
    )
    missing = [token for token in mandatory if token not in text]
    if missing:
        raise ProbeError("source contract missing mandatory probe anchors: " + ", ".join(missing))

    cpp = CppSource(text)
    insertions: list[tuple[int, str]] = []
    active: list[str] = []
    unavailable: dict[str, str] = {}
    try:
        body = cpp.function_body("QPXThermalDiffusionMaterial::evaluate")
        insertions.append(_timer_after_brace(text, body.start, "evaluate", 1))
        active.append("evaluate")
        for key, token in {
            "functor_DT": "_D_T_names",
            "functor_kT": "_kT_names",
            "functor_Dmix": "_D_mix_names",
        }.items():
            lambda_body = cpp.lambda_body(cpp.unique_call("addFunctorProperty", containing=token))
            insertions.append(_timer_after_brace(text, lambda_body.start, key, 2))
            active.append(key)
    except CppSourceError as exc:
        raise ProbeError(f"source structure contract failed: {exc}") from exc

    for key, token, pattern, required_depth in (
        ("dmix", "one_minus_Y", r"one_minus_Y\s*=\s*1\.0\s*-\s*Y\s*\[\s*i\s*\]", 1),
        ("collision_pairs", "nDij", r"nDij\s*\[\s*i\s*\]\s*\[\s*j\s*\]\s*=", 2),
    ):
        if token not in text:
            unavailable[key] = f"{token} anchor not present"
            continue
        try:
            loops = cpp.enclosing_blocks(pattern, keyword="for")
            if len(loops) >= required_depth:
                insertions.extend(_wrap_for_timer(text, loops[required_depth - 1], key, 2))
                active.append(key)
            elif key == "dmix":
                unavailable[key] = "D_mix anchor found but no enclosing for-loop"
            else:
                unavailable[key] = "pair assignment is not enclosed by two identifiable for-loop bodies"
        except (CppSourceError, ProbeError) as exc:
            unavailable[key] = str(exc)

    includes = []
    for header in ("MooseApp.h", "PerfGraphRegistry.h", "PerfGuard.h"):
        if f'#include "{header}"' not in text:
            includes.append(f'#include "{header}"\n')
    matches = list(re.finditer(r"^#include[^\n]*\n", text, re.MULTILINE))
    insertions.append((matches[-1].end() if matches else 0, "".join(includes) + _support_block()))

    instrumented = text
    for idx, payload in sorted(insertions, key=lambda item: item[0], reverse=True):
        instrumented = instrumented[:idx] + payload + instrumented[idx:]
    if instrumented == text:
        raise ProbeError("instrumentation produced no source change")
    if _has_legacy_time_section(instrumented):
        raise ProbeError("direct probe unexpectedly emitted legacy TIME_SECTION")

    primary = ("evaluate", "functor_DT", "functor_kT", "functor_Dmix")
    for key in primary:
        if instrumented.count(TIMER_NAMES[key]) != 1:
            raise ProbeError(f"mandatory direct timer marker {TIMER_NAMES[key]} count is not exactly one")
    for key in ("collision_pairs", "dmix"):
        count = instrumented.count(TIMER_NAMES[key])
        if key in active and count != 1:
            raise ProbeError(f"active optional timer {TIMER_NAMES[key]} count is not exactly one")
        if key not in active and count != 0:
            raise ProbeError(f"inactive optional timer {TIMER_NAMES[key]} unexpectedly present")
    return instrumented, {
        "timers": dict(TIMER_NAMES),
        "active_timers": active,
        "unavailable_timers": unavailable,
        "primary_discriminator_ready": all(key in active for key in primary),
        "timing_backend": "PerfGraphRegistry+PerfGuard",
        "header_mutation_required": False,
    }


def _optional_seconds(timer: dict[str, float | int]) -> float | None:
    return None if int(timer.get("node_count", 0)) <= 0 else float(timer.get("inclusive_seconds", 0.0))


def analyze_probe(profile_result: dict[str, Any], perfgraph_path: Path) -> dict[str, Any]:
    """Analyze direct probe evidence while tolerating unused optional timers."""
    try:
        rows = perfgraph.read_rows(perfgraph_path)
        timers = {key: perfgraph.sum_timer(rows, name) for key, name in TIMER_NAMES.items()}
        jac_timers = {
            key: perfgraph.sum_timer(rows, name, ancestor_contains="jacobian")
            for key, name in TIMER_NAMES.items()
        }
    except perfgraph.PerfGraphError as exc:
        raise ProbeError(str(exc)) from exc

    wall = float(profile_result.get("performance", {}).get("wall_seconds") or 0.0)
    if wall <= 0:
        raise ProbeError("profile wall time missing")
    if int(timers["evaluate"]["node_count"]) == 0:
        raise ProbeError("mandatory instrumented timer was not captured: evaluate")
    runtime_capture = {key: int(timers[key]["node_count"]) > 0 for key in TIMER_NAMES}

    jacobian_seconds = 0.0
    petsc = profile_result.get("performance", {}).get("petsc")
    if isinstance(petsc, dict):
        for row in petsc.get("rows", []):
            if isinstance(row, dict) and row.get("Event Name") == "SNESJacobianEval" and row.get("Rank") in (None, "", 0, "0", 0.0):
                try:
                    jacobian_seconds += float(row.get("Time", 0.0))
                except (TypeError, ValueError):
                    pass
    if jacobian_seconds <= 0:
        jacobian_seconds = sum(float(row["self_seconds"]) for row in rows if "jacobian" in str(row["name"]).lower())

    evaluate_all = float(timers["evaluate"]["inclusive_seconds"])
    evaluate_jac = float(jac_timers["evaluate"]["inclusive_seconds"])
    fraction_wall = evaluate_all / wall
    fraction_jac = evaluate_jac / jacobian_seconds if jacobian_seconds > 0 else None
    if fraction_jac is not None and fraction_jac >= 0.50:
        outcome = "APPLICATION_EVALUATION_INSIDE_JACOBIAN"
        confidence = "high" if fraction_jac >= 0.70 else "medium"
        reason = f"instrumented heavy-transport evaluate accounts for {fraction_jac:.1%} of Jacobian time"
    elif fraction_jac is not None and fraction_jac <= 0.20:
        outcome = "JACOBIAN_AD_RETAINED"
        confidence = "high" if fraction_jac <= 0.10 else "medium"
        reason = f"instrumented heavy-transport evaluate accounts for only {fraction_jac:.1%} of Jacobian time"
    elif fraction_wall >= 0.25:
        outcome = "APPLICATION_EVALUATION_MATERIAL"
        confidence = "medium"
        reason = f"instrumented heavy-transport evaluate accounts for {fraction_wall:.1%} of wall time"
    else:
        outcome = "MIXED_OR_FURTHER_LOCALIZATION"
        confidence = "low"
        reason = "heavy-transport evaluate is material but not sufficiently separated from remaining Jacobian cost"

    return {
        "analysis_status": "PASS",
        "outcome": outcome,
        "confidence": confidence,
        "reason": reason,
        "wall_seconds": wall,
        "jacobian_seconds": jacobian_seconds,
        "evaluate_fraction_of_wall": fraction_wall,
        "evaluate_fraction_of_jacobian": fraction_jac,
        "evaluate_self_seconds": float(timers["evaluate"]["self_seconds"]),
        "evaluate_inclusive_seconds": evaluate_all,
        "evaluate_jacobian_context_seconds": evaluate_jac,
        "collision_pair_seconds": _optional_seconds(timers["collision_pairs"]),
        "dmix_seconds": _optional_seconds(timers["dmix"]),
        "timers": timers,
        "jacobian_context_timers": jac_timers,
        "runtime_capture": runtime_capture,
        "fine_grained_coverage": {key: runtime_capture[key] for key in ("functor_DT", "functor_kT", "functor_Dmix", "collision_pairs", "dmix")},
        "functor_call_counts": {key: int(timers[key]["num_calls"]) for key in ("functor_DT", "functor_kT", "functor_Dmix", "evaluate")},
    }


def _fixture_source(*, nested_pairs: bool = True) -> str:
    pair = """for (int i = 0; i < 7; ++i)\n  {\n    for (int j = 0; j < 7; ++j)\n    {\n      nDij[i][j] = i + j;\n    }\n  }""" if nested_pairs else """for (int i = 0; i < 7; ++i)\n  {\n    nDij[i][j] = helper(i);\n  }"""
    return f'''#include "SomeHeader.h"
QPXThermalDiffusionMaterial::QPXThermalDiffusionMaterial()
{{
  addFunctorProperty<ADReal>(_D_T_names[i], [this, i](const auto & r, const auto & state) {{
    return evaluate(r, state).D_T[i];
  }});
  addFunctorProperty<ADReal>(_kT_names[i], [this, i](const auto & r, const auto & state) {{
    return evaluate(r, state).kT[i];
  }});
  addFunctorProperty<ADReal>(_D_mix_names[i], [this, i](const auto & r, const auto & state) {{
    return evaluate(r, state).D_mix[i];
  }});
}}
Result
QPXThermalDiffusionMaterial::evaluate(const int r, const int state) const
{{
  auto nDij = foo();
  {pair}
  for (int i = 0; i < 7; ++i)
  {{
    const ADReal one_minus_Y = 1.0 - Y[i];
    D_mix[i] = one_minus_Y / denominator;
  }}
  return out;
}}
'''


def _fixture_perfgraph(*, include_functors: bool) -> dict[str, Any]:
    children: dict[str, Any] = {
        TIMER_NAMES["evaluate"]: {"level": 2, "time": 6.0, "num_calls": 10, "children": {}}
    }
    if include_functors:
        for key in ("functor_DT", "functor_kT", "functor_Dmix"):
            children[TIMER_NAMES[key]] = {"level": 2, "time": 0.1, "num_calls": 10, "children": {}}
    return {"reporters": {"pg": {"type": "PerfGraphReporter"}}, "time_steps": [{"pg": {"version": 1, "graph": {"app": {"level": 0, "time": 1.0, "num_calls": 1, "children": {"NonlinearSystemBase::computeJacobianInternal": {"level": 1, "time": 4.0, "num_calls": 1, "children": children}}}}}}]}


def self_test() -> int:
    try:
        nested, meta = instrument_source(_fixture_source())
        if not meta["primary_discriminator_ready"] or meta["timing_backend"] != "PerfGraphRegistry+PerfGuard" or meta["header_mutation_required"]:
            raise AssertionError("direct instrumentation metadata drift")
        for required in ('#include "MooseApp.h"', '#include "PerfGraphRegistry.h"', '#include "PerfGuard.h"', PROBE_MACRO, "getMooseApp().perfGraph()"):
            if required not in nested:
                raise AssertionError(f"missing direct PerfGraph support: {required}")
        if _has_legacy_time_section(nested):
            raise AssertionError("legacy TIME_SECTION remained in direct probe")

        flat, flat_meta = instrument_source(_fixture_source(nested_pairs=False))
        if "collision_pairs" in flat_meta["active_timers"] or "collision_pairs" not in flat_meta["unavailable_timers"]:
            raise AssertionError("single-loop collision capability drift")
        try:
            instrument_source(flat)
        except ProbeError:
            pass
        else:
            raise AssertionError("reinstrumentation negative control passed")
        try:
            instrument_source(_fixture_source().replace("_D_mix_names", "missing", 1))
        except ProbeError:
            pass
        else:
            raise AssertionError("missing-functor negative control passed")

        profile = {"performance": {"wall_seconds": 20.0, "petsc": {"rows": [{"Event Name": "SNESJacobianEval", "Rank": 0, "Time": 10.0, "Count": 1}]}}}
        with tempfile.TemporaryDirectory() as tmp_name:
            path = Path(tmp_name) / "perf.json"
            path.write_text(json.dumps(_fixture_perfgraph(include_functors=True)))
            result = analyze_probe(profile, path)
            if result["outcome"] != "APPLICATION_EVALUATION_INSIDE_JACOBIAN" or not math.isclose(float(result["evaluate_fraction_of_jacobian"]), 0.6, rel_tol=1e-12):
                raise AssertionError("direct analysis discriminator drift")
            if result["collision_pair_seconds"] is not None:
                raise AssertionError("missing optional timer should remain null")
            path.write_text(json.dumps(_fixture_perfgraph(include_functors=False)))
            sparse = analyze_probe(profile, path)
            if sparse["analysis_status"] != "PASS" or any(sparse["runtime_capture"][key] for key in ("functor_DT", "functor_kT", "functor_Dmix")):
                raise AssertionError("unused-functor tolerance drift")
            path.write_text(json.dumps({"reporters": {}, "time_steps": []}))
            try:
                analyze_probe(profile, path)
            except ProbeError:
                pass
            else:
                raise AssertionError("invalid-PerfGraph negative control passed")
        print("QPX_TRANSPORT_PROBE_DIRECT_SELFTEST: PASS")
        return 0
    except Exception as exc:
        print(f"QPX_TRANSPORT_PROBE_DIRECT_SELFTEST: FAIL: {exc}")
        return 1
