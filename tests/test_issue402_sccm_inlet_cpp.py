"""Build and execute the actual pure C++ SCCM module without a MOOSE binary.

P0 only: exact historical Issue #19 reference, JSON-inspired mixed feed,
invalid-domain mutations and stable Postprocessor name mappings.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "physics_app/src/physics/plasma/SCCMInletFlow.C"
GAS_STATE_SRC = ROOT / "physics_app/src/physics/plasma/IdealGasMixtureState.C"
INC = ROOT / "physics_app/include/physics/plasma"


def test_standalone_sccm_cpp_oracle(tmp_path: Path):
    compiler = shutil.which("c++") or shutil.which("g++")
    if compiler is None:
        pytest.skip("No host C++ compiler: P0 C++ unit unverified; native P1 remains required")

    driver = tmp_path / "sccm_oracle.C"
    binary = tmp_path / "sccm_oracle"
    driver.write_text(r'''
#include "SCCMInletFlow.h"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>

using Plasma::SCCMFeedSettings;
using Plasma::SCCMFeedSpecies;
using Plasma::SCCMInletFlow;

bool near(const double a, const double b, const double eps = 1e-12)
{
  return std::abs(a - b) <= eps * std::max(std::abs(a), std::abs(b));
}

bool rejects(const SCCMFeedSettings & p, const std::vector<SCCMFeedSpecies> & s)
{
  try
  {
    (void)SCCMInletFlow::calculate(p, s);
    return false;
  }
  catch (const std::invalid_argument &)
  {
    return true;
  }
}

int main()
{
  const SCCMFeedSettings base{100.0, 0.05954574715614091, 0.0224136, 1.33322, 300.0};
  const std::vector<SCCMFeedSpecies> oxygen{{"O2", 1.0, 0.032},
                                             {"O", 0.0, 0.016}};
  const auto a = SCCMInletFlow::calculate(base, oxygen);
  const double accepted = 2.3795076798610368e-6; // pinned Issue #19 expected.json
  if (!near(a.at("plasma_inlet_mdot"), accepted, 1e-13))
    return 1;
  if (!near(a.at("plasma_inlet_mass_flux"),
            accepted / base.inlet_area_m2))
    return 2;
  if (!near(a.at("plasma_inlet_rho"),
            base.inlet_pressure_pa * 0.032 / (8.31446261815324 * base.inlet_temperature_k)))
    return 3;
  if (!near(a.at("plasma_inlet_speed"),
            a.at("plasma_inlet_mdot") / (a.at("plasma_inlet_area") *
                                            a.at("plasma_inlet_rho"))))
    return 4;
  if (a.at("plasma_inlet_mdot_O") != 0.0 ||
      !near(a.at("plasma_inlet_mdot_O2"), accepted))
    return 5;

  auto double_flow = base;
  double_flow.sccm *= 2;
  const auto doubled = SCCMInletFlow::calculate(double_flow, oxygen);
  if (!near(doubled.at("plasma_inlet_mdot"), 2 * accepted))
    return 6;

  const std::vector<SCCMFeedSpecies> mixed{{"O2", 0.75, 0.032},
                                            {"O", 0.25, 0.016},
                                            {"Op", 0.0, 0.016}};
  const auto m = SCCMInletFlow::calculate(base, mixed);
  const double mix_m = 1.0 / (0.75 / 0.032 + 0.25 / 0.016);
  const double reference = base.sccm * 1e-6 / 60 * mix_m /
                           base.standard_molar_volume_m3_per_mol;
  if (!near(m.at("plasma_inlet_mdot"), reference) ||
      !near(m.at("plasma_inlet_mdot_O"), 0.25 * reference) ||
      m.at("plasma_inlet_mdot_Op") != 0.0)
    return 7;
  if (near(m.at("plasma_inlet_mdot"), accepted, 1e-4))
    return 8; // wrong mixture mass mutation must be detected
  if (!near(m.at("plasma_inlet_mdot_O2") + m.at("plasma_inlet_mdot_O") +
            m.at("plasma_inlet_mdot_Op"), reference))
    return 9;

  auto bad_area = base;
  bad_area.inlet_area_m2 = 0;
  auto bad_vm = base;
  bad_vm.standard_molar_volume_m3_per_mol = -0.1;
  auto bad_q = base;
  bad_q.sccm = 0;
  if (!rejects(bad_area, oxygen) || !rejects(bad_vm, oxygen) ||
      !rejects(bad_q, oxygen))
    return 10;
  if (!rejects(base, {{"O2", 0.8, 0.032}, {"O", 0.0, 0.016}}))
    return 11; // missing feed mass fraction
  if (!rejects(base, {{"O2", 0.75, 0.032}, {"O2", 0.25, 0.032}}))
    return 12; // duplicate species IDs
  if (!rejects(base, {{"O2", -0.1, 0.032}, {"O", 1.1, 0.016}}))
    return 13; // unphysical fractions
  if (!rejects(base, {{"O2", 1.0, 0.0}}))
    return 14; // no positive molar mass

  std::cout << "SCCM_PURE_CPP_P0_PASS\n";
  return 0;
}
''')
    compile_result = subprocess.run(
        [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-I", str(INC), str(SRC), str(GAS_STATE_SRC), str(driver), "-o", str(binary)],
        capture_output=True, text=True, check=False,
    )
    assert compile_result.returncode == 0, (
        f"Pure C++ SCCM compilation failed:\n{compile_result.stdout}\n{compile_result.stderr}"
    )
    run = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
    assert run.returncode == 0, (
        f"Pure C++ SCCM mutation failed, exit code {run.returncode}: "
        f"{run.stdout} {run.stderr}"
    )
    assert "SCCM_PURE_CPP_P0_PASS" in run.stdout
