#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

EPS0 = 8.8541878128e-12
E_CHARGE = 1.602176634e-19
NA = 6.02214076e23
MU_E = 9755.114369721427
RHO = 1.3793506167141378e-5
M_O2P = 0.032
NE0 = 1.0e16
FINAL_TAU = 20.0

ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "generated"

CASES = (
    {"name": "ref_chi0p1", "chi": 0.1, "steps": 200, "fp_min": 1, "fp_max": 1},
    {"name": "onepass_chi5", "chi": 5.0, "steps": 4, "fp_min": 1, "fp_max": 1},
    {"name": "gummel_chi5", "chi": 5.0, "steps": 4, "fp_min": 2, "fp_max": 30},
)


def tau_epsilon() -> float:
    return EPS0 / (E_CHARGE * MU_E * NE0)


def _render(template: str, replacements: dict[str, str]) -> str:
    text = template
    for key, value in replacements.items():
        token = f"@@{key}@@"
        if text.count(token) == 0:
            raise RuntimeError(f"template token missing: {token}")
        text = text.replace(token, value)
    leftovers = sorted(set(part.split("@@", 1)[0] for part in text.split("@@")[1::2]))
    if "@@" in text:
        raise RuntimeError(f"unresolved template token(s): {leftovers}")
    return text


def case_parameters(spec: dict[str, object]) -> dict[str, object]:
    tau = tau_epsilon()
    chi = float(spec["chi"])
    dt = chi * tau
    end_time = FINAL_TAU * tau
    steps = int(spec["steps"])
    if not math.isclose(dt * steps, end_time, rel_tol=1e-14, abs_tol=1e-30):
        raise RuntimeError(
            f"{spec['name']}: dt*steps={dt * steps:.17g} != end_time={end_time:.17g}"
        )
    log_ce = math.log(NE0 / NA)
    w_o2p = NE0 * M_O2P / (RHO * NA)
    return {
        "name": str(spec["name"]),
        "chi": chi,
        "tau_epsilon_s": tau,
        "dt_s": dt,
        "end_time_s": end_time,
        "steps": steps,
        "fp_min": int(spec["fp_min"]),
        "fp_max": int(spec["fp_max"]),
        "log_ce0": log_ce,
        "w_O2p0": w_o2p,
        "ne0_m3": NE0,
    }


def build(clean: bool = True) -> list[dict[str, object]]:
    electron_template = (ROOT / "electron_template.i").read_text(encoding="utf-8")
    poisson_template = (ROOT / "poisson_template.i").read_text(encoding="utf-8")
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    built: list[dict[str, object]] = []
    for spec in CASES:
        params = case_parameters(spec)
        case_dir = GENERATED / str(params["name"])
        case_dir.mkdir(parents=True, exist_ok=True)
        common = {
            "LOG_CE": f"{params['log_ce0']:.17g}",
            "W_O2P": f"{params['w_O2p0']:.17g}",
            "NE0": f"{params['ne0_m3']:.17g}",
        }
        electron = _render(
            electron_template,
            {
                **common,
                "CASE_NAME": str(params["name"]),
                "DT": f"{params['dt_s']:.17g}",
                "END_TIME": f"{params['end_time_s']:.17g}",
                "STEPS": str(params["steps"]),
                "TIMESTEP_TOL": f"{max(float(params['dt_s']) * 1.0e-6, 1.0e-30):.17g}",
                "FP_MIN": str(params["fp_min"]),
                "FP_MAX": str(params["fp_max"]),
            },
        )
        poisson = _render(
            poisson_template,
            {"LOG_CE": common["LOG_CE"], "W_O2P": common["W_O2P"]},
        )
        (case_dir / "input.i").write_text(electron, encoding="utf-8")
        (case_dir / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        (case_dir / "case.json").write_text(
            json.dumps(params, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        built.append(params)

    (GENERATED / "matrix.json").write_text(
        json.dumps(
            {
                "issue": 253,
                "objective": "chi=5 one-pass versus converged Gummel against chi=0.1 reference",
                "electron_energy_equation": False,
                "mean_electron_energy_eV": 5.73276,
                "chemistry": False,
                "rf_heating": False,
                "heavy_evolution": False,
                "cases": built,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return built


def static_contract() -> dict[str, object]:
    built = build()
    by_name = {str(x["name"]): x for x in built}
    ref = by_name["ref_chi0p1"]
    one = by_name["onepass_chi5"]
    gum = by_name["gummel_chi5"]

    assert ref["chi"] == 0.1 and ref["steps"] == 200 and ref["fp_max"] == 1
    assert one["chi"] == 5.0 and one["steps"] == 4 and one["fp_max"] == 1
    assert gum["chi"] == 5.0 and gum["steps"] == 4 and gum["fp_min"] == 2
    assert gum["fp_max"] == 30
    assert math.isclose(float(one["dt_s"]), float(gum["dt_s"]), rel_tol=0.0, abs_tol=0.0)
    assert math.isclose(
        float(ref["end_time_s"]), float(one["end_time_s"]), rel_tol=0.0, abs_tol=0.0
    )

    for name in by_name:
        text = (GENERATED / name / "input.i").read_text(encoding="utf-8")
        assert "PhysicsFVLogMolarElectronTimeDerivative" in text
        assert "PhysicsFVLogMolarElectrostaticDrift" in text
        assert "potential = potential_from_poisson" in text
        assert "FullSolveMultiApp" in text
        assert "execute_on = TIMESTEP_END" in text
        assert "auto_advance = true" in text
        assert "c_epsilon" not in text
        assert "PhysicsFVLogMolarElectronEnergy" not in text
        assert "@@" not in text

        poisson = (GENERATED / name / "poisson_sub.i").read_text(encoding="utf-8")
        assert "automatic_scaling = true" in poisson
        assert "off_diagonals_in_auto_scaling" not in poisson
        assert "compute_scaling_once" not in poisson

    return {
        "status": "PASS",
        "tau_epsilon_s": tau_epsilon(),
        "cases": built,
        "historical_relaxation_anchor": "5ddb47e0a3bf0b22e50b78c31490361cd749309b",
        "claim": "historical particle-Poisson model preserved; only dt and fixed-point coupling differ",
    }


if __name__ == "__main__":
    summary = static_contract()
    print("ISSUE253_G1_P1: PASS")
    print(json.dumps(summary, indent=2, sort_keys=True))
