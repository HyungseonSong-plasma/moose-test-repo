from __future__ import annotations

import json
from pathlib import Path

from experiments.Issue92_r3_nonlinear.inspect_artifact import fallback_parse, inspect


def _runtime_log() -> str:
    return """Time Step 1, time = 1e-08, dt = 1e-08
 0 Nonlinear |R| = 9.839955e-01
    |residual|_2 of individual variables:
                     u:     1.0e-03
                     v:     2.0e-03
                     p:     3.0e-03
                     w_O2p: 4.0e-03
                     n_e:   9.0e-01
 1 Nonlinear |R| = 1.033670e+00
    |residual|_2 of individual variables:
                     u:     1.0e-03
                     v:     2.0e-03
                     p:     3.0e-03
                     w_O2p: 4.0e-03
                     n_e:   9.5e-01
"""


def test_fallback_parse_accepts_current_moose_residual_output() -> None:
    parsed = fallback_parse(_runtime_log())
    assert parsed["global_residual_count"] == 2
    assert parsed["variable_table_count"] == 2
    assert parsed["dominant_groups"] == ["ELECTRON", "ELECTRON"]
    assert parsed["detected_variable_headers"] == [
        "|residual|_2 of individual variables:",
        "|residual|_2 of individual variables:",
    ]


def test_inspector_reads_existing_b7_artifact_without_qpx(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "d1_residual_anatomy.log").write_text(_runtime_log())
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "selected_branch": "B7",
                "terminal_reason": "DIAGNOSTIC_OUTPUT_INCOMPLETE_OR_CONFIGURATION_MISMATCH",
                "d1": {
                    "global_residuals": [0.9839955, 1.03367],
                    "variable_norms": [],
                    "parse_complete": False,
                },
            }
        )
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "subruns": [
                    {
                        "name": "D1",
                        "run": {"returncode": 0, "timed_out": False},
                    }
                ]
            }
        )
    )

    result = inspect(tmp_path)
    assert result["prior_selected_branch"] == "B7"
    assert result["runtime_returncode"] == 0
    assert result["runtime_timed_out"] is False
    assert result["prior_parser"]["variable_table_count"] == 0
    assert result["fallback"]["variable_table_count"] == 2
    assert result["diagnosis"] == "FALLBACK_PARSE_COMPLETE"
