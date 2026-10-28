#include "PhysicsBoltzmannElasticSolver.h"

#include <cassert>
#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace PhysicsBoltzmann;

static ElasticInput fixture(std::size_t cells, double EN_Td)
{
  ElasticInput input;
  input.cells = cells;
  input.max_energy_eV = 2.0;
  input.gas_temperature_K = 300.0;
  input.reduced_field_Td = EN_Td;
  input.targets.push_back({"synthetic-argon-like", 1.0, 1.37e-5,
                           {0.0, 2.0}, {5e-20, 5e-20}});
  return input;
}

static void reject(const std::function<void()> & action)
{
  try { action(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("expected input validation error");
}

static double relativeError(double a, double b)
{
  return std::abs(a - b) / std::max(std::abs(b), 1e-300);
}

int main()
{
  // Exact zero-field, finite-gas-temperature analytic invariant:
  // f0(e) proportional to exp(-e/kT), mean(e) tends to 3kT/2.
  constexpr double theta = 1.380649e-23 * 300.0 / 1.602176634e-19;
  const auto coarse = solveElasticSteadyState(fixture(200, 0.0));
  const auto fine = solveElasticSteadyState(fixture(800, 0.0));
  const auto finer = solveElasticSteadyState(fixture(3200, 0.0));
  const double err_c = relativeError(coarse.mean_energy_eV, 1.5 * theta);
  const double err_f = relativeError(fine.mean_energy_eV, 1.5 * theta);
  const double err_ff = relativeError(finer.mean_energy_eV, 1.5 * theta);
  if (!(err_f < err_c && err_ff < err_f && err_ff < 1e-3))
    throw std::runtime_error("Maxwellian mean energy failed refinement");
  if (!(coarse.maximum_normalized_flux_residual < 1e-12 &&
        finer.maximum_normalized_flux_residual < 1e-12))
    throw std::runtime_error("nonzero numerical energy flux in conservative equilibrium");

  for (const auto & result : {coarse, fine, finer})
  {
    double integral = 0.0;
    const double h = 2.0 / result.energy_eV.size();
    for (std::size_t i = 0; i < result.energy_eV.size(); ++i)
    {
      const double a = i * h, b = (i + 1) * h;
      const double f = result.eepf_eV_minus_3_halves[i];
      if (!std::isfinite(f) || f < 0.0)
        throw std::runtime_error("non-finite or negative EEPF");
      integral += f * (2.0 / 3.0) * (std::pow(b, 1.5) - std::pow(a, 1.5));
    }
    if (std::abs(integral - 1.0) > 2e-12)
      throw std::runtime_error("EEPF normalization failed");
  }

  // High fields must increase mean energy for this elastic-only fixture;
  // no claim of quantitative argon/BOLSIG+ parity is made.
  auto low = fixture(1000, 0.05);
  auto high = fixture(1000, 0.2);
  const auto result_low = solveElasticSteadyState(low);
  const auto result_high = solveElasticSteadyState(high);
  if (!(fine.mean_energy_eV < result_low.mean_energy_eV &&
        result_low.mean_energy_eV < result_high.mean_energy_eV))
    throw std::runtime_error("DC field heating response is inconsistent");
  if (result_high.maximum_normalized_flux_residual > 1e-12)
    throw std::runtime_error("SG exponential flux balance failed");

  // P0 negative controls: reject malformed units, coverages, fractions,
  // sign errors, nonmonotone energies and absent physical collision operators.
  auto bad = fixture(100, 1.0);
  bad.targets[0].mole_fraction = 0.4;
  reject([&] { (void)solveElasticSteadyState(bad); });
  bad = fixture(100, 1.0);
  bad.targets[0].momentum_transfer_m2[0] = -1.0;
  reject([&] { (void)solveElasticSteadyState(bad); });
  bad = fixture(100, 1.0);
  bad.targets[0].energy_eV[1] = 0.0;
  reject([&] { (void)solveElasticSteadyState(bad); });
  bad = fixture(100, 1.0);
  bad.targets[0].momentum_transfer_m2 = {0, 0};
  reject([&] { (void)solveElasticSteadyState(bad); });
  bad = fixture(100, 1.0);
  bad.targets[0].energy_eV.back() = 1.0;
  reject([&] { (void)solveElasticSteadyState(bad); });
  bad = fixture(100, -1.0);
  reject([&] { (void)solveElasticSteadyState(bad); });

  std::cout << "BOLTZMANN_ELASTIC_P0_P1_PASS\n"
            << "MAXWELL_REFINEMENT_ERRORS=" << err_c << ',' << err_f << ',' << err_ff << '\n'
            << "FIELD_MEAN_ENERGIES_EV=" << fine.mean_energy_eV << ','
            << result_low.mean_energy_eV << ',' << result_high.mean_energy_eV << '\n'
            << "MAX_NORMALIZED_FLUX_RESIDUAL=" << result_high.maximum_normalized_flux_residual
            << '\n';
}
