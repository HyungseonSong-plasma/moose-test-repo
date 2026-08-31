#!/usr/bin/env python3
"""P0 characterization for transport-probe C++ and PerfGraph primitives."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import cpp_source
from qpx_harness import perfgraph
from qpx_harness import performance_transport_probe_direct as direct


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

    instrumented, metadata = direct.instrument_source(source)
    if not metadata.get("primary_discriminator_ready"):
        raise AssertionError("direct probe did not accept generic C++ structural contract")
    if set(metadata.get("active_timers", ())) != set(direct.TIMER_NAMES):
        raise AssertionError("direct probe active-timer coverage drift")
    for timer in direct.TIMER_NAMES.values():
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
    for key, timer in direct.TIMER_NAMES.items():
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
        expected_rows, direct.TIMER_NAMES["evaluate"], ancestor_contains="residual"
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

    test_source = Path(__file__).read_text()
    if "from qpx_harness import performance_transport_probe as" in test_source:
        raise AssertionError("WP9 still imports the retired legacy oracle")


def main() -> int:
    try:
        if cpp_source.self_test() != 0:
            raise AssertionError("CppSource self-test failed")
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
