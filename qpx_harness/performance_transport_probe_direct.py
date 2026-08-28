"""Direct-PerfGraph PF-3 transport probe adapter.

QPXThermalDiffusionMaterial is a MooseObject but does not inherit
PerfGraphInterface.  Therefore MOOSE's TIME_SECTION macro cannot be used in
that class.  This adapter keeps the probe source-only by registering sections
with the global PerfGraphRegistry and timing them with PerfGuard using the
public MooseObject::getMooseApp().perfGraph() path.
"""

from __future__ import annotations

import json
import math
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from . import performance_transport_probe as legacy
from . import performance_transport_probe_resilient as resilient

TIMER_NAMES = legacy.TIMER_NAMES
MARKER_PREFIX = legacy.MARKER_PREFIX
ProbeError = legacy.ProbeError
PROBE_MACRO = "QPX_TRANSPORT_TIME_SECTION"


def _timer_call(key: str, level: int) -> str:
    return f'{PROBE_MACRO}({key}, "{TIMER_NAMES[key]}", {level});'


def _timer_after_brace(text: str, brace_idx: int, key: str, level: int) -> tuple[int, str]:
    line_start = text.rfind("\n", 0, brace_idx) + 1
    match = re.match(r"[ \t]*", text[line_start:brace_idx])
    indent = (match.group(0) if match else "") + "  "
    call = _timer_call(key, level)
    if brace_idx + 1 < len(text) and text[brace_idx + 1] == "\n":
        payload = f"\n{indent}{call}"
    else:
        payload = f"\n{indent}{call}\n{indent}"
    return brace_idx + 1, payload


def _wrap_for_timer(text: str, span: tuple[int, int], key: str, level: int) -> list[tuple[int, str]]:
    marker = "__qpx_direct_placeholder__"
    wrapped = legacy._wrap_for_timer(text, span, marker, level)
    old = f'TIME_SECTION("{marker}", {level});'
    new = _timer_call(key, level)
    converted = [(idx, payload.replace(old, new)) for idx, payload in wrapped]
    if all(old in payload for _, payload in converted):
        raise ProbeError(f"failed to convert loop timer for {key}")
    return converted


def _support_block() -> str:
    return '''\n#ifndef QPX_TRANSPORT_TIME_SECTION\n#define QPX_TRANSPORT_TIME_SECTION(token, section_name, level)                                  \\
  static const PerfID token##_perf_id = []() {                                                  \\
    auto & registry = moose::internal::getPerfGraphRegistry();                                  \\
    return registry.sectionExists(section_name) ? registry.sectionID(section_name)               \\
                                                : registry.registerSection(section_name, level);  \\
  }();                                                                                            \\
  PerfGuard token##_perf_guard(getMooseApp().perfGraph(), token##_perf_id)\n#endif\n'''


def _has_legacy_time_section(text: str) -> bool:
    return re.search(r"\bTIME_SECTION\s*\(", text) is not None


def instrument_source(text: str) -> tuple[str, dict[str, Any]]:
    """Add source-only PerfGuard instrumentation without PerfGraphInterface inheritance."""

    if MARKER_PREFIX in text or PROBE_MACRO in text:
        raise ProbeError("source already contains qpx transport instrumentation markers")

    mandatory_tokens = [
        "QPXThermalDiffusionMaterial::evaluate",
        "_D_T_names",
        "_kT_names",
        "_D_mix_names",
    ]
    missing = [token for token in mandatory_tokens if token not in text]
    if missing:
        raise ProbeError(
            "source contract missing mandatory probe anchors: " + ", ".join(missing)
        )

    insertions: list[tuple[int, str]] = []
    active: list[str] = []
    unavailable: dict[str, str] = {}

    body_open, _ = legacy._find_function_body(
        text, "QPXThermalDiffusionMaterial::evaluate"
    )
    insertions.append(_timer_after_brace(text, body_open, "evaluate", 1))
    active.append("evaluate")

    for key, token in {
        "functor_DT": "_D_T_names",
        "functor_kT": "_kT_names",
        "functor_Dmix": "_D_mix_names",
    }.items():
        brace, _ = legacy._find_add_functor_lambda_body(text, token)
        insertions.append(_timer_after_brace(text, brace, key, 2))
        active.append(key)

    if "one_minus_Y" in text:
        try:
            dmix_for = legacy._enclosing_for_blocks(
                text, r"one_minus_Y\s*=\s*1\.0\s*-\s*Y\s*\[\s*i\s*\]"
            )
            if dmix_for:
                insertions.extend(_wrap_for_timer(text, dmix_for[0], "dmix", 2))
                active.append("dmix")
            else:
                unavailable["dmix"] = "D_mix anchor found but no enclosing for-loop"
        except ProbeError as exc:
            unavailable["dmix"] = str(exc)
    else:
        unavailable["dmix"] = "D_mix anchor not present"

    if "nDij" in text:
        try:
            pair_for = legacy._enclosing_for_blocks(
                text, r"nDij\s*\[\s*i\s*\]\s*\[\s*j\s*\]\s*="
            )
            if len(pair_for) >= 2:
                insertions.extend(
                    _wrap_for_timer(text, pair_for[1], "collision_pairs", 2)
                )
                active.append("collision_pairs")
            else:
                unavailable["collision_pairs"] = (
                    "pair assignment is not enclosed by two identifiable for-loop bodies"
                )
        except ProbeError as exc:
            unavailable["collision_pairs"] = str(exc)
    else:
        unavailable["collision_pairs"] = "nDij anchor not present"

    include_lines: list[str] = []
    for header in ("MooseApp.h", "PerfGraphRegistry.h", "PerfGuard.h"):
        if f'#include "{header}"' not in text:
            include_lines.append(f'#include "{header}"\n')
    include_matches = list(re.finditer(r"^#include[^\n]*\n", text, re.MULTILINE))
    support_at = include_matches[-1].end() if include_matches else 0
    support = "".join(include_lines) + _support_block()
    insertions.append((support_at, support))

    instrumented = text
    for idx, payload in sorted(insertions, key=lambda item: item[0], reverse=True):
        instrumented = instrumented[:idx] + payload + instrumented[idx:]

    if instrumented == text:
        raise ProbeError("instrumentation produced no source change")
    if _has_legacy_time_section(instrumented):
        raise ProbeError("direct probe unexpectedly emitted legacy TIME_SECTION")

    mandatory = ("evaluate", "functor_DT", "functor_kT", "functor_Dmix")
    for key in mandatory:
        if instrumented.count(TIMER_NAMES[key]) != 1:
            raise ProbeError(
                f"mandatory direct timer marker {TIMER_NAMES[key]} count is not exactly one"
            )

    for key in ("collision_pairs", "dmix"):
        count = instrumented.count(TIMER_NAMES[key])
        if key in active and count != 1:
            raise ProbeError(
                f"active optional timer {TIMER_NAMES[key]} count is not exactly one"
            )
        if key not in active and count != 0:
            raise ProbeError(
                f"inactive optional timer {TIMER_NAMES[key]} unexpectedly present"
            )

    return instrumented, {
        "timers": dict(TIMER_NAMES),
        "active_timers": active,
        "unavailable_timers": unavailable,
        "primary_discriminator_ready": all(key in active for key in mandatory),
        "timing_backend": "PerfGraphRegistry+PerfGuard",
        "header_mutation_required": False,
    }


def self_test() -> int:
    try:
        nested, nested_meta = instrument_source(legacy._synthetic_source())
        if not nested_meta["primary_discriminator_ready"]:
            raise AssertionError("primary discriminator not ready")
        if nested_meta["timing_backend"] != "PerfGraphRegistry+PerfGuard":
            raise AssertionError("wrong timing backend")
        if nested_meta["header_mutation_required"]:
            raise AssertionError("direct probe must remain source-only")
        for required in (
            '#include "MooseApp.h"',
            '#include "PerfGraphRegistry.h"',
            '#include "PerfGuard.h"',
            PROBE_MACRO,
            "getMooseApp().perfGraph()",
        ):
            if required not in nested:
                raise AssertionError(f"missing direct PerfGraph support: {required}")
        if _has_legacy_time_section(nested):
            raise AssertionError("legacy TIME_SECTION remained in direct probe")

        flat, flat_meta = instrument_source(resilient._single_loop_source())
        if "collision_pairs" in flat_meta["active_timers"]:
            raise AssertionError("single-loop collision path falsely treated as nested")
        if flat.count(TIMER_NAMES["evaluate"]) != 1:
            raise AssertionError("evaluate timer missing")

        try:
            instrument_source(flat)
        except ProbeError:
            pass
        else:
            raise AssertionError("reinstrumentation mutation was not rejected")

        perfgraph = {
            "reporters": {"pg": {"type": "PerfGraphReporter"}},
            "time_steps": [{
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
                                            "time": 6.0,
                                            "num_calls": 10,
                                            "children": {}
                                        },
                                        "qpx_transport_functor_DT": {
                                            "level": 2,
                                            "time": 0.1,
                                            "num_calls": 10,
                                            "children": {}
                                        },
                                        "qpx_transport_functor_kT": {
                                            "level": 2,
                                            "time": 0.1,
                                            "num_calls": 10,
                                            "children": {}
                                        },
                                        "qpx_transport_functor_Dmix": {
                                            "level": 2,
                                            "time": 0.1,
                                            "num_calls": 10,
                                            "children": {}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }]
        }
        profile = {
            "performance": {
                "wall_seconds": 20.0,
                "petsc": {
                    "rows": [{
                        "Event Name": "SNESJacobianEval",
                        "Rank": 0,
                        "Time": 10.0,
                        "Count": 1
                    }]
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            perf_path = Path(tmp) / "perf.json"
            perf_path.write_text(json.dumps(perfgraph))
            result = resilient.analyze_probe(profile, perf_path)
            if result["outcome"] != "APPLICATION_EVALUATION_INSIDE_JACOBIAN":
                raise AssertionError(result)
            if not math.isclose(
                float(result["evaluate_fraction_of_jacobian"]), 0.6, rel_tol=1e-12
            ):
                raise AssertionError("Jacobian fraction self-test")

        print("QPX_TRANSPORT_PROBE_DIRECT_SELFTEST: PASS")
        return 0
    except Exception as exc:
        print(f"QPX_TRANSPORT_PROBE_DIRECT_SELFTEST: FAIL: {exc}")
        return 1


def _activate() -> None:
    legacy.instrument_source = instrument_source
    legacy.analyze_probe = resilient.analyze_probe


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv) if argv is not None else list(sys.argv[1:])
    if "--self-test" in args:
        return self_test()
    _activate()
    return legacy.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
