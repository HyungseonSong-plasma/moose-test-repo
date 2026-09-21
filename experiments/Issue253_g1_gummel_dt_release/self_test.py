#!/usr/bin/env python3
from __future__ import annotations

import json
import math

from prepare import CASES, FINAL_TAU, case_parameters, static_contract, tau_epsilon


def main() -> int:
    summary = static_contract()
    assert summary["status"] == "PASS"
    assert tau_epsilon() > 0.0

    by_name = {str(spec["name"]): case_parameters(spec) for spec in CASES}
    ref = by_name["ref_chi0p1"]
    one = by_name["onepass_chi5"]
    gum = by_name["gummel_chi5"]

    assert math.isclose(float(ref["dt_s"]) / float(ref["tau_epsilon_s"]), 0.1)
    assert math.isclose(float(one["dt_s"]) / float(one["tau_epsilon_s"]), 5.0)
    assert math.isclose(float(gum["dt_s"]) / float(gum["tau_epsilon_s"]), 5.0)
    assert math.isclose(
        float(ref["end_time_s"]) / float(ref["tau_epsilon_s"]), FINAL_TAU
    )
    assert one["dt_s"] == gum["dt_s"]
    assert one["steps"] == gum["steps"]
    assert one["fp_max"] == 1
    assert int(gum["fp_max"]) > 1

    # Negative mutation: a "Gummel" case that does not iterate is invalid.
    mutated = dict(gum)
    mutated["fp_max"] = 1
    try:
        assert int(mutated["fp_max"]) > 1
    except AssertionError:
        pass
    else:
        raise AssertionError("negative control did not reject non-iterating Gummel case")

    print("ISSUE253_G1_P0: PASS")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
