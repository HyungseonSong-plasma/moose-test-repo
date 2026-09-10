#!/usr/bin/env python3
"""P0 characterization for transport-probe C++ and PerfGraph primitives."""
from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics_harness.adapters.moose.performance import perfgraph
from physics_harness.observation.source_code import cpp as cpp_source


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


class HistoricalTransportProbeError(RuntimeError):
    """Test-only error for the retired PF-3 direct instrumentation contract."""


def _timer_call(key: str, level: int) -> str:
    return f'{PROBE_MACRO}({key}, "{TIMER_NAMES[key]}", {level});'


def _timer_after_brace(text: str, brace: int, key: str, level: int) -> tuple[int, str]:
    line_start = text.rfind("\n", 0, brace) + 1
    match = re.match(r"[ \t]*", text[line_start:brace])
    indent = (match.group(0) if match else "") + "  "
    call = _timer_call(key, level)
    payload = (
        f"\n{indent}{call}"
        if brace + 1 < len(text) and text[brace + 1] == "\n"
        else f"\n{indent}{call}\n{indent}"
    )
    return brace + 1, payload


def _wrap_for_timer(
    text: str,
    span: cpp_source.Span,
    key: str,
    level: int,
) -> list[tuple[int, str]]:
    cpp = cpp_source.CppSource(text)
    close_idx = span.end - 1
    i = span.start - 1
    while i >= 0 and cpp.masked[i].isspace():
        i -= 1
    if i < 0 or cpp.masked[i] != ")":
        raise HistoricalTransportProbeError("for-loop instrumentation expected ')' before body")
    try:
        open_paren = cpp.match_backward(i, "(", ")")
    except cpp_source.CppSourceError as exc:
        raise HistoricalTransportProbeError(str(exc)) from exc
    j = open_paren - 1
    while j >= 0 and cpp.masked[j].isspace():
        j -= 1
    end = j + 1
    while j >= 0 and (cpp.masked[j].isalnum() or cpp.masked[j] == "_"):
        j -= 1
    if cpp.masked[j + 1 : end] != "for":
        raise HistoricalTransportProbeError("instrumentation span is not a for-loop body")
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


def _instrument_source(text: str) -> tuple[str, dict[str, object]]:
    """Preserve the retired PF-3 direct PerfGraph instrumentation contract."""
    if MARKER_PREFIX in text or PROBE_MACRO in text:
        raise HistoricalTransportProbeError(
            "source already contains qpx transport instrumentation markers"
        )
    mandatory = (
        "QPXThermalDiffusionMaterial::evaluate",
        "_D_T_names",
        "_kT_names",
        "_D_mix_names",
    )
    missing = [token for token in mandatory if token not in text]
    if missing:
        raise HistoricalTransportProbeError(
            "source contract missing mandatory probe anchors: " + ", ".join(missing)
        )

    cpp = cpp_source.CppSource(text)
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
    except cpp_source.CppSourceError as exc:
        raise HistoricalTransportProbeError(f"source structure contract failed: {exc}") from exc

    for key, token, pattern, required_depth in (
        (
            "dmix",
            "one_minus_Y",
            r"one_minus_Y\s*=\s*1\.0\s*-\s*Y\s*\[\s*i\s*\]",
            1,
        ),
        (
            "collision_pairs",
            "nDij",
            r"nDij\s*\[\s*i\s*\]\s*\[\s*j\s*\]\s*=",
            2,
        ),
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
                unavailable[key] = (
                    "pair assignment is not enclosed by two identifiable for-loop bodies"
                )
        except (cpp_source.CppSourceError, HistoricalTransportProbeError) as exc:
            unavailable[key] = str(exc)

    includes = []
    for header in ("MooseApp.h", "PerfGraphRegistry.h", "PerfGuard.h"):
        if f'#include "{header}"' not in text:
            includes.append(f'#include "{header}"\n')
    matches = list(re.finditer(r"^#include[^\n]*\n", text, re.MULTILINE))
    insertions.append(
        (matches[-1].end() if matches else 0, "".join(includes) + _support_block())
    )

    instrumented = text
    for idx, payload in sorted(insertions, key=lambda item: item[0], reverse=True):
        instrumented = instrumented[:idx] + payload + instrumented[idx:]
    if instrumented == text:
        raise HistoricalTransportProbeError("instrumentation produced no source change")
    if _has_legacy_time_section(instrumented):
        raise HistoricalTransportProbeError("direct probe unexpectedly emitted legacy TIME_SECTION")

    primary = ("evaluate", "functor_DT", "functor_kT", "functor_Dmix")
    for key in primary:
        if instrumented.count(TIMER_NAMES[key]) != 1:
            raise HistoricalTransportProbeError(
                f"mandatory direct timer marker {TIMER_NAMES[key]} count is not exactly one"
            )
    for key in ("collision_pairs", "dmix"):
        count = instrumented.count(TIMER_NAMES[key])
        if key in active and count != 1:
            raise HistoricalTransportProbeError(
                f"active optional timer {TIMER_NAMES[key]} count is not exactly one"
            )
        if key not in active and count != 0:
            raise HistoricalTransportProbeError(
                f"inactive optional timer {TIMER_NAMES[key]} unexpectedly present"
            )
    return instrumented, {
        "timers": dict(TIMER_NAMES),
        "active_timers": active,
        "unavailable_timers": unavailable,
        "primary_discriminator_ready": all(key in active for key in primary),
        "timing_backend": "PerfGraphRegistry+PerfGuard",
        "header_mutation_required": False,
    }


def _transport_source_fixture() -> str:
    return '''#include "SomeHeader.h"
QPXThermalDiffusionMaterial::QPXThermalDiffusionMaterial()
{
  addFunctorProperty<ADReal>(_D_T_names[i], [this, i](const auto & r, const auto & state) {
    return evaluate(r, state).D_T[i];
  });
  addFunctorProperty<ADReal>(_kT_names[i], [this, i](const auto & r, const auto & state) {
    return evaluate(r, state).kT[i];
  });
  addFunctorProperty<ADReal>(_D_mix_names[i], [this, i](const auto & r, const auto & state) {
    return evaluate(r, state).D_mix[i];
  });
}
Result
QPXThermalDiffusionMaterial::evaluate(const int r, const int state) const
{
  auto nDij = foo();
  for (int i = 0; i < 7; ++i)
  {
    for (int j = 0; j < 7; ++j)
    {
      nDij[i][j] = i + j;
    }
  }
  for (int i = 0; i < 7; ++i)
  {
    const ADReal one_minus_Y = 1.0 - Y[i];
    for (int j = 0; j < 7; ++j)
      denominator += X[j] / (nDij[i][j] / number_density);
    D_mix[i] = one_minus_Y / denominator;
  }
  return out;
}
'''


def _check_cpp_contract() -> None:
    source = _transport_source_fixture()
    cpp = cpp_source.CppSource(source)

    body = cpp.function_body("QPXThermalDiffusionMaterial::evaluate")
    body_text = body.slice(source)
    if not body_text.startswith("{") or not body_text.endswith("}"):
        raise AssertionError("function-body structural boundary drift")
    for token in ("nDij[i][j]", "one_minus_Y", "return out"):
        if token not in body_text:
            raise AssertionError(f"function-body fixture token missing: {token}")

    dmix_blocks = cpp.enclosing_blocks(
        r"one_minus_Y\s*=\s*1\.0\s*-\s*Y\s*\[\s*i\s*\]", keyword="for"
    )
    if len(dmix_blocks) != 1:
        raise AssertionError(f"expected one braced D_mix loop, found {len(dmix_blocks)}")

    pair_blocks = cpp.enclosing_blocks(
        r"nDij\s*\[\s*i\s*\]\s*\[\s*j\s*\]\s*=", keyword="for"
    )
    if len(pair_blocks) != 2:
        raise AssertionError(f"expected nested pair loops, found {len(pair_blocks)}")
    if (pair_blocks[0].end - pair_blocks[0].start) >= (
        pair_blocks[1].end - pair_blocks[1].start
    ):
        raise AssertionError("enclosing for-loop order is not inner-to-outer")

    for token in ("_D_T_names", "_kT_names", "_D_mix_names"):
        call = cpp.unique_call("addFunctorProperty", containing=token)
        lambda_body = cpp.lambda_body(call).slice(source)
        if "return evaluate" not in lambda_body:
            raise AssertionError(f"lambda-body contract drift: {token}")

    instrumented, metadata = _instrument_source(source)
    if not metadata.get("primary_discriminator_ready"):
        raise AssertionError("direct probe did not accept generic C++ structural contract")
    if set(metadata.get("active_timers", ())) != set(TIMER_NAMES):
        raise AssertionError("direct probe active-timer coverage drift")
    for timer in TIMER_NAMES.values():
        if instrumented.count(timer) != 1:
            raise AssertionError(f"direct timer insertion drift: {timer}")

    try:
        cpp_source.CppSource(source.replace("_D_mix_names", "missing", 1)).unique_call(
            "addFunctorProperty", containing="_D_mix_names"
        )
    except cpp_source.CppSourceError:
        pass
    else:
        raise AssertionError("missing-functor negative control passed")


def _perfgraph_payload() -> dict:
    return {
        "reporters": {"pg": {"type": "PerfGraphReporter"}},
        "time_steps": [
            {
                "pg": {
                    "version": 1,
                    "graph": {
                        "app": {
                            "level": 0,
                            "time": 1.0,
                            "num_calls": 1,
                            "children": {
                                "NonlinearSystemBase::computeJacobianInternal": {
                                    "level": 1,
                                    "time": 4.0,
                                    "num_calls": 1,
                                    "children": {
                                        "qpx_transport_evaluate": {
                                            "level": 2,
                                            "time": 3.0,
                                            "num_calls": 10,
                                            "children": {
                                                "qpx_transport_dmix": {
                                                    "level": 3,
                                                    "time": 1.0,
                                                    "num_calls": 10,
                                                    "children": {},
                                                }
                                            },
                                        }
                                    },
                                }
                            },
                        }
                    },
                }
            }
        ],
    }


def _check_perfgraph_contract() -> None:
    payload = _perfgraph_payload()
    expected_rows = [
        {
            "name": "qpx_transport_dmix",
            "path": [
                "app",
                "NonlinearSystemBase::computeJacobianInternal",
                "qpx_transport_evaluate",
                "qpx_transport_dmix",
            ],
            "self_seconds": 1.0,
            "inclusive_seconds": 1.0,
            "num_calls": 10,
        },
        {
            "name": "qpx_transport_evaluate",
            "path": [
                "app",
                "NonlinearSystemBase::computeJacobianInternal",
                "qpx_transport_evaluate",
            ],
            "self_seconds": 3.0,
            "inclusive_seconds": 4.0,
            "num_calls": 10,
        },
        {
            "name": "NonlinearSystemBase::computeJacobianInternal",
            "path": ["app", "NonlinearSystemBase::computeJacobianInternal"],
            "self_seconds": 4.0,
            "inclusive_seconds": 8.0,
            "num_calls": 1,
        },
        {
            "name": "app",
            "path": ["app"],
            "self_seconds": 1.0,
            "inclusive_seconds": 9.0,
            "num_calls": 1,
        },
    ]
    if perfgraph.rows_from_payload(payload) != expected_rows:
        raise AssertionError("PerfGraph exact row contract drift")

    with tempfile.TemporaryDirectory() as tmp_name:
        path = Path(tmp_name) / "perf.json"
        path.write_text(json.dumps(payload))
        if perfgraph.read_rows(path) != expected_rows:
            raise AssertionError("PerfGraph file-read contract drift")

    expected_evaluate = {
        "self_seconds": 3.0,
        "inclusive_seconds": 4.0,
        "num_calls": 10,
        "node_count": 1,
    }
    expected_dmix = {
        "self_seconds": 1.0,
        "inclusive_seconds": 1.0,
        "num_calls": 10,
        "node_count": 1,
    }
    zero = {
        "self_seconds": 0,
        "inclusive_seconds": 0,
        "num_calls": 0,
        "node_count": 0,
    }
    for key, timer in TIMER_NAMES.items():
        expected = (
            expected_evaluate
            if key == "evaluate"
            else expected_dmix
            if key == "dmix"
            else zero
        )
        actual = perfgraph.sum_timer(expected_rows, timer)
        if actual != expected:
            raise AssertionError((key, actual, expected))
        jac = perfgraph.sum_timer(expected_rows, timer, ancestor_contains="jacobian")
        if jac != expected:
            raise AssertionError((f"jac:{key}", jac, expected))

    if perfgraph.sum_timer(
        expected_rows, TIMER_NAMES["evaluate"], ancestor_contains="residual"
    ) != zero:
        raise AssertionError("ancestor-filter negative control passed")

    bad = dict(payload)
    bad["reporters"] = {
        "a": {"type": "PerfGraphReporter"},
        "b": {"type": "PerfGraphReporter"},
    }
    try:
        perfgraph.rows_from_payload(bad)
    except perfgraph.PerfGraphError:
        pass
    else:
        raise AssertionError("multiple-reporter negative control passed")


def _imports_qpx_harness(path: Path) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").startswith("qpx_harness"):
                return True
        elif isinstance(node, ast.Import):
            if any(alias.name.startswith("qpx_harness") for alias in node.names):
                return True
    return False


def _check_boundary() -> None:
    source = Path(perfgraph.__file__).read_text()
    for forbidden in (
        "performance_transport_probe",
        "Issue43",
        "Issue48",
        "qpx_transport_",
    ):
        if forbidden in source:
            raise AssertionError(f"PerfGraph primitive leaked caller semantics: {forbidden}")

    if _imports_qpx_harness(Path(__file__)):
        raise AssertionError("WP9 still imports the retired qpx_harness namespace")


def main() -> int:
    try:
        if perfgraph.self_test() != 0:
            raise AssertionError("PerfGraph self-test failed")
        _check_cpp_contract()
        _check_perfgraph_contract()
        _check_boundary()
    except Exception as exc:
        print(f"ISSUE48_TRANSPORT_PROBE_PRIMITIVES_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_TRANSPORT_PROBE_PRIMITIVES_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
