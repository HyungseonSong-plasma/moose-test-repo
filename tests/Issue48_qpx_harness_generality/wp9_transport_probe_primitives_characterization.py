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
from qpx_harness import performance_transport_probe as legacy


def _check_cpp_equivalence() -> None:
    source = legacy._synthetic_source()
    cpp = cpp_source.CppSource(source)

    signature = "QPXThermalDiffusionMaterial::evaluate"
    body = cpp.function_body(signature)
    if (body.start, body.end - 1) != legacy._find_function_body(source, signature):
        raise AssertionError("function-body span drift")

    anchors = (
        r"one_minus_Y\s*=\s*1\.0\s*-\s*Y\s*\[\s*i\s*\]",
        r"nDij\s*\[\s*i\s*\]\s*\[\s*j\s*\]\s*=",
    )
    for anchor in anchors:
        actual = [(span.start, span.end - 1) for span in cpp.enclosing_blocks(anchor, keyword="for")]
        expected = legacy._enclosing_for_blocks(source, anchor)
        if actual != expected:
            raise AssertionError((anchor, actual, expected))

    for token in ("_D_T_names", "_kT_names", "_D_mix_names"):
        call = cpp.unique_call("addFunctorProperty", containing=token)
        body = cpp.lambda_body(call)
        actual = (body.start, body.end - 1)
        expected = legacy._find_add_functor_lambda_body(source, token)
        if actual != expected:
            raise AssertionError((token, actual, expected))

    try:
        cpp_source.CppSource(source.replace("_D_mix_names", "missing", 1)).unique_call(
            "addFunctorProperty", containing="_D_mix_names"
        )
    except cpp_source.CppSourceError:
        pass
    else:
        raise AssertionError("missing-functor negative control passed")


def _check_perfgraph_equivalence() -> None:
    payload = {
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
    with tempfile.TemporaryDirectory() as tmp_name:
        path = Path(tmp_name) / "perf.json"
        path.write_text(json.dumps(payload))
        expected_rows = legacy._walk_perfgraph(path)
        actual_rows = perfgraph.read_rows(path)
        if actual_rows != expected_rows:
            raise AssertionError("PerfGraph row equivalence drift")

        for timer in legacy.TIMER_NAMES.values():
            expected = legacy._sum_timer(expected_rows, timer)
            actual = perfgraph.sum_timer(actual_rows, timer)
            if actual != expected:
                raise AssertionError((timer, actual, expected))
            expected_jac = legacy._sum_timer(expected_rows, timer, jacobian_only=True)
            actual_jac = perfgraph.sum_timer(
                actual_rows, timer, ancestor_contains="jacobian"
            )
            if actual_jac != expected_jac:
                raise AssertionError((timer, actual_jac, expected_jac))

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


def main() -> int:
    try:
        if cpp_source.self_test() != 0:
            raise AssertionError("CppSource self-test failed")
        if perfgraph.self_test() != 0:
            raise AssertionError("PerfGraph self-test failed")
        _check_cpp_equivalence()
        _check_perfgraph_equivalence()
        _check_boundary()
    except Exception as exc:
        print(f"ISSUE48_TRANSPORT_PROBE_PRIMITIVES_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_TRANSPORT_PROBE_PRIMITIVES_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
