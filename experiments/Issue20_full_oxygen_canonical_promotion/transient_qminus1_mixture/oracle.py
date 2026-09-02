#!/usr/bin/env python3
from __future__ import annotations
import math
import sys

R = 8.31446
P = 13.332
T = 600.0

M = {
    "O2": 0.032, "O2s": 0.032, "O2p": 0.032,
    "O": 0.016, "Om": 0.016, "Op": 0.016, "Os": 0.016,
}

def close(six):
    y_o2 = 1.0 - sum(six.values())
    Y = {"O2": y_o2, **six}
    mn = 1.0 / sum(Y[k] / M[k] for k in Y)
    rho = P * mn / (R * T)
    return Y, mn, rho

def self_test():
    six_a = {
        "O2s": 0.045, "O2p": 0.012, "O": 0.18,
        "Om": 0.013, "Op": 0.013, "Os": 0.13,
    }
    six_b = {
        "O2s": 0.044, "O2p": 0.011, "O": 0.14,
        "Om": 0.011, "Op": 0.011, "Os": 0.11,
    }

    for label, six in [("A", six_a), ("B", six_b)]:
        Y, mn, rho = close(six)
        assert abs(sum(Y.values()) - 1.0) < 1e-15
        assert min(Y.values()) >= 0.0
        assert 0.016 <= mn <= 0.032
        assert rho > 0.0
        assert abs(rho - P*mn/(R*T)) < 1e-18
        print(f"{label}: O2={Y['O2']:.12e} Mn={mn:.12e} rho={rho:.12e}")

    _, mn_a, rho_a = close(six_a)
    _, mn_b, rho_b = close(six_b)
    dt = 1.0e-4
    dmn = (mn_b - mn_a) / dt
    drho = (rho_b - rho_a) / dt
    scale = P/(R*T)
    rel = abs(drho - scale*dmn) / max(abs(drho), 1e-300)
    assert rel < 1e-13
    print(f"DISCRETE_DERIVATIVE_IDENTITY_REL={rel:.3e}")

    # Negative controls
    wrong_rho = P*0.032/(R*T)
    assert abs(wrong_rho-rho_a)/rho_a > 1e-2
    wrong_o2 = 1.0 + sum(six_a.values())
    assert abs(wrong_o2 + sum(six_a.values()) - 1.0) > 1e-2

    print("R14_EVR1D_ORACLE_SELFTEST: PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(self_test())
