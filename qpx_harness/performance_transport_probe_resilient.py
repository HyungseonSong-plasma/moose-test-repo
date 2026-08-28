"""Resilient PF-3 transport probe adapter.

Source instrumentation is capability-based instead of requiring one specific
C++ loop shape.  The evaluate timer is the mandatory runtime discriminator;
functor and fine-grained timers are optional runtime evidence because a valid
case may not request every declared functor.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from . import performance_transport_probe as legacy

TIMER_NAMES = legacy.TIMER_NAMES
MARKER_PREFIX = legacy.MARKER_PREFIX
ProbeError = legacy.ProbeError


def instrument_source(text: str) -> tuple[str, dict[str, Any]]:
    if MARKER_PREFIX in text:
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
    insertions.append(
        legacy._timer_after_brace(text, body_open, TIMER_NAMES["evaluate"], 1)
    )
    active.append("evaluate")

    for key, token in {
        "functor_DT": "_D_T_names",
        "functor_kT": "_kT_names",
        "functor_Dmix": "_D_mix_names",
    }.items():
        brace, _ = legacy._find_add_functor_lambda_body(text, token)
        insertions.append(legacy._timer_after_brace(text, brace, TIMER_NAMES[key], 2))
        active.append(key)

    if "one_minus_Y" in text:
        try:
            dmix_for = legacy._enclosing_for_blocks(
                text, r"one_minus_Y\s*=\s*1\.0\s*-\s*Y\s*\[\s*i\s*\]"
            )
            if dmix_for:
                insertions.extend(
                    legacy._wrap_for_timer(text, dmix_for[0], TIMER_NAMES["dmix"], 2)
                )
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
                    legacy._wrap_for_timer(
                        text, pair_for[1], TIMER_NAMES["collision_pairs"], 2
                    )
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

    if "PerfGraphInterface.h" not in text:
        import re

        include = '#include "PerfGraphInterface.h"\n'
        matches = list(re.finditer(r"^#include[^\n]*\n", text, re.MULTILINE))
        insertions.append((matches[-1].end() if matches else 0, include))

    instrumented = text
    for idx, payload in sorted(insertions, key=lambda item: item[0], reverse=True):
        instrumented = instrumented[:idx] + payload + instrumented[idx:]

    if instrumented == text:
        raise ProbeError("instrumentation produced no source change")

    source_required = ("evaluate", "functor_DT", "functor_kT", "functor_Dmix")
    for key in source_required:
        name = TIMER_NAMES[key]
        if instrumented.count(name) != 1:
            raise ProbeError(f"required source timer marker {name} count is not exactly one")

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
        "primary_discriminator_ready": "evaluate" in active,
    }


def _optional_seconds(timer: dict[str, float | int]) -> float | None:
    if int(timer.get("node_count", 0)) <= 0:
        return None
    return float(timer.get("inclusive_seconds", 0.0))


def analyze_probe(profile_result: dict[str, Any], perfgraph_path: Path) -> dict[str, Any]:
    rows = legacy._walk_perfgraph(perfgraph_path)
    wall = float(profile_result.get("performance", {}).get("wall_seconds") or 0.0)
    if wall <= 0:
        raise ProbeError("profile wall time missing")

    timers = {key: legacy._sum_timer(rows, name) for key, name in TIMER_NAMES.items()}
    jac_timers = {
        key: legacy._sum_timer(rows, name, jacobian_only=True)
        for key, name in TIMER_NAMES.items()
    }

    if int(timers["evaluate"]["node_count"]) == 0:
        raise ProbeError("mandatory instrumented timer was not captured: evaluate")

    runtime_capture = {
        key: int(timers[key]["node_count"]) > 0
        for key in TIMER_NAMES
    }

    jacobian_seconds = 0.0
    petsc = profile_result.get("performance", {}).get("petsc")
    if isinstance(petsc, dict):
        for row in petsc.get("rows", []):
            if (
                isinstance(row, dict)
                and row.get("Event Name") == "SNESJacobianEval"
                and row.get("Rank") in (None, "", 0, "0", 0.0)
            ):
                try:
                    jacobian_seconds += float(row.get("Time", 0.0))
                except (TypeError, ValueError):
                    pass
    if jacobian_seconds <= 0:
        jacobian_seconds = sum(
            float(row["self_seconds"])
            for row in rows
            if "jacobian" in row["name"].lower()
        )

    evaluate_all = float(timers["evaluate"]["inclusive_seconds"])
    evaluate_jac = float(jac_timers["evaluate"]["inclusive_seconds"])
    fraction_wall = evaluate_all / wall
    fraction_jac = evaluate_jac / jacobian_seconds if jacobian_seconds > 0 else None

    if fraction_jac is not None and fraction_jac >= 0.50:
        outcome = "APPLICATION_EVALUATION_INSIDE_JACOBIAN"
        confidence = "high" if fraction_jac >= 0.70 else "medium"
        reason = (
            f"instrumented heavy-transport evaluate accounts for {fraction_jac:.1%} "
            "of Jacobian time"
        )
    elif fraction_jac is not None and fraction_jac <= 0.20:
        outcome = "JACOBIAN_AD_RETAINED"
        confidence = "high" if fraction_jac <= 0.10 else "medium"
        reason = (
            f"instrumented heavy-transport evaluate accounts for only {fraction_jac:.1%} "
            "of Jacobian time"
        )
    elif fraction_wall >= 0.25:
        outcome = "APPLICATION_EVALUATION_MATERIAL"
        confidence = "medium"
        reason = (
            f"instrumented heavy-transport evaluate accounts for {fraction_wall:.1%} "
            "of wall time"
        )
    else:
        outcome = "MIXED_OR_FURTHER_LOCALIZATION"
        confidence = "low"
        reason = (
            "heavy-transport evaluate is material but not sufficiently separated "
            "from remaining Jacobian cost"
        )

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
        "fine_grained_coverage": {
            key: runtime_capture[key]
            for key in ("functor_DT", "functor_kT", "functor_Dmix", "collision_pairs", "dmix")
        },
        "functor_call_counts": {
            key: int(timers[key]["num_calls"])
            for key in ("functor_DT", "functor_kT", "functor_Dmix", "evaluate")
        },
    }


def _single_loop_source() -> str:
    return r'''#include "SomeHeader.h"
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
    nDij[i][j] = helper(i);
  }
  for (int i = 0; i < 7; ++i)
  {
    const ADReal one_minus_Y = 1.0 - Y[i];
    D_mix[i] = one_minus_Y / denominator;
  }
  return out;
}
'''


def _synthetic_perfgraph(include_functors: bool) -> dict[str, Any]:
    children: dict[str, Any] = {
        "QPXThermalDiffusionMaterial::qpx_transport_evaluate": {
            "level": 2,
            "time": 6.0,
            "num_calls": 10,
            "children": {},
        }
    }
    if include_functors:
        for suffix in ("DT", "kT", "Dmix"):
            children[f"QPXThermalDiffusionMaterial::qpx_transport_functor_{suffix}"] = {
                "level": 2,
                "time": 0.1,
                "num_calls": 10,
                "children": {},
            }
    return {
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
                                "children": children,
                            }
                        },
                    }
                },
            }
        }],
    }


def self_test() -> int:
    try:
        nested, nested_meta = instrument_source(legacy._synthetic_source())
        if not nested_meta["primary_discriminator_ready"]:
            raise AssertionError("primary discriminator not ready")
        for key in ("evaluate", "functor_DT", "functor_kT", "functor_Dmix"):
            if nested.count(TIMER_NAMES[key]) != 1:
                raise AssertionError(f"required source timer missing: {key}")

        flat, flat_meta = instrument_source(_single_loop_source())
        if "collision_pairs" in flat_meta["active_timers"]:
            raise AssertionError("single-loop collision path was falsely treated as nested")
        if "collision_pairs" not in flat_meta["unavailable_timers"]:
            raise AssertionError("missing optional-collision capability was not recorded")
        if flat.count(TIMER_NAMES["evaluate"]) != 1:
            raise AssertionError("flat-source evaluate timer missing")

        try:
            instrument_source(flat)
        except ProbeError:
            pass
        else:
            raise AssertionError("reinstrumentation mutation was not rejected")

        profile = {
            "performance": {
                "wall_seconds": 20.0,
                "petsc": {
                    "rows": [{
                        "Event Name": "SNESJacobianEval",
                        "Rank": 0,
                        "Time": 10.0,
                        "Count": 1,
                    }]
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            perf_path = Path(tmp) / "perf.json"
            perf_path.write_text(json.dumps(_synthetic_perfgraph(include_functors=True)))
            result = analyze_probe(profile, perf_path)
            if result["outcome"] != "APPLICATION_EVALUATION_INSIDE_JACOBIAN":
                raise AssertionError(result)
            if not math.isclose(
                float(result["evaluate_fraction_of_jacobian"]), 0.6, rel_tol=1e-12
            ):
                raise AssertionError("Jacobian fraction self-test")
            if result["collision_pair_seconds"] is not None:
                raise AssertionError("optional missing timer should remain null")

            perf_path.write_text(json.dumps(_synthetic_perfgraph(include_functors=False)))
            sparse_result = analyze_probe(profile, perf_path)
            if sparse_result["analysis_status"] != "PASS":
                raise AssertionError("missing unused functors must not fail analysis")
            for key in ("functor_DT", "functor_kT", "functor_Dmix"):
                if sparse_result["runtime_capture"][key]:
                    raise AssertionError(f"unused functor unexpectedly captured: {key}")
                if sparse_result["functor_call_counts"][key] != 0:
                    raise AssertionError(f"unused functor call count not zero: {key}")

        print("QPX_TRANSPORT_PROBE_RESILIENT_SELFTEST: PASS")
        return 0
    except Exception as exc:
        print(f"QPX_TRANSPORT_PROBE_RESILIENT_SELFTEST: FAIL: {exc}")
        return 1


def _activate() -> None:
    legacy.instrument_source = instrument_source
    legacy.analyze_probe = analyze_probe


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv) if argv is not None else list(sys.argv[1:])
    if "--self-test" in args:
        return self_test()
    _activate()
    return legacy.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
