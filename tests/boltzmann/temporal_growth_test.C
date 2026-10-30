#include "PhysicsBoltzmannTemporalGrowth.h"

#include <algorithm>
#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>

using namespace PhysicsBoltzmann;

namespace
{
ElasticInput fixture(std::size_t n)
{
  ElasticInput a;
  a.max_energy_eV = 2.0;
  a.cells = n;
  a.reduced_field_Td = 0.1;
  a.gas_temperature_K = 3000.0;
  a.targets = {{"synthetic-Ar", 1.0, 1.37e-5,
                {0.0, 2.0}, {5e-20, 5e-20}}};
  return a;
}
IonizationChannel ion(double sigma)
{
  return {"synthetic-ion", "synthetic-Ar", 0.35,
          {0.0, 2.0}, {sigma, sigma}};
}
AttachmentChannel attachment(double sigma)
{
  return {"synthetic-attachment", "synthetic-Ar",
          {0.0, 2.0}, {sigma, sigma}};
}
void reject(const std::function<void()> & fn)
{
  try { fn(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("Boltzmann M6b: expected invalid input rejection");
}
void audit(const TemporalGrowthResult & result, const ElasticInput & in)
{
  if (!(result.inverse_iterations > 0 && result.inverse_iterations <= 8000 &&
        result.maximum_normalized_eigen_residual < 1e-8 &&
        result.distribution.mean_energy_eV > 0.0 &&
        result.distribution.mean_energy_eV < in.max_energy_eV))
    throw std::runtime_error("Boltzmann M6b: temporal growth eigenpair failed");
  double norm = 0.0;
  const double h = in.max_energy_eV / in.cells;
  for (std::size_t i = 0; i < in.cells; ++i)
  {
    const double f = result.distribution.eepf_eV_minus_3_halves[i];
    if (!std::isfinite(f) || f < 0.0)
      throw std::runtime_error("Boltzmann M6b: negative growth eigenfunction");
    norm += f * (2.0 / 3.0) * (std::pow((i + 1) * h, 1.5) -
                                std::pow(i * h, 1.5));
  }
  if (std::abs(norm - 1.0) > 1e-10)
    throw std::runtime_error("Boltzmann M6b: eigen-EEPF not normalized");
  const double exact_rates = result.growth.reduced_temporal_growth_m3_per_s;
  if (std::abs(exact_rates - result.reduced_growth_eigenvalue_m3_per_s) >
          1e-12 * (std::abs(exact_rates) + 1e-30))
    throw std::runtime_error("Boltzmann M6b: eigenvalue and reaction growth rates disagree");
}
} // namespace

int main()
{
  for (const std::size_t n : {50u, 100u})
  {
    const auto input = fixture(n);
    const auto ion_only = solveElasticTemporalGrowth(input, {ion(1e-20)}, {});
    const auto att_only = solveElasticTemporalGrowth(input, {}, {attachment(1e-20)});
    audit(ion_only, input);
    audit(att_only, input);
    if (!(ion_only.reduced_growth_eigenvalue_m3_per_s > 0.0 &&
          att_only.reduced_growth_eigenvalue_m3_per_s < 0.0))
      throw std::runtime_error("Boltzmann M6b: wrong temporal-growth eigenvalue signs");

    // Weak-growth limit recovers the M1 conservative stationary EEPF:
    // the distribution is NOT arbitrarily frozen in the new eigen solve.
    const auto weak = solveElasticTemporalGrowth(input, {ion(1e-25)}, {});
    audit(weak, input);
    const auto elastic = solveElasticSteadyState(input);
    const double difference = std::abs(weak.distribution.mean_energy_eV -
                                       elastic.mean_energy_eV);
    if (!(difference < 0.03))
      throw std::runtime_error("Boltzmann M6b: weak-growth/M1 EEPF continuity failed");
  }

  const auto input = fixture(100);
  const auto mixed = solveElasticTemporalGrowth(input,
                                               {ion(1e-20)}, {attachment(2e-21)});
  audit(mixed, input);
  const double expected =
      mixed.growth.ionization_rates_m3_per_s[0] -
      mixed.growth.attachment_rates_m3_per_s[0];
  if (std::abs(expected - mixed.reduced_growth_eigenvalue_m3_per_s) >
          1e-12 * (std::abs(expected) + 1e-30))
    throw std::runtime_error("Boltzmann M6b: net growth rate does not close");

  // The 200-cell native Example 4 resolution is now admissible on the
  // development-only dense reference path. Recheck normalized eigenpair
  // residual, signed growth and the weak-growth elastic limit at 200 cells.
  const auto native_grid = fixture(200);
  const auto refined_growth =
      solveElasticTemporalGrowth(native_grid, {ion(1e-25)}, {});
  audit(refined_growth, native_grid);
  const auto refined_elastic = solveElasticSteadyState(native_grid);
  if (!(refined_growth.reduced_growth_eigenvalue_m3_per_s > 0.0 &&
        std::abs(refined_growth.distribution.mean_energy_eV -
                 refined_elastic.mean_energy_eV) < 0.03))
    throw std::runtime_error("Boltzmann M6b4: 200-cell weak-growth parity failed");

  auto large = fixture(257);
  reject([&] { (void)solveElasticTemporalGrowth(large, {ion(1e-20)}, {}); });
  auto bad = fixture(100);
  bad.targets[0].mole_fraction = 0.8;
  reject([&] { (void)solveElasticTemporalGrowth(bad, {ion(1e-20)}, {}); });

  std::cout << "BOLTZMANN_M6B4_200_CELL_TEMPORAL_GROWTH_P0_P1_PASS\n";
  std::cout << "BOLTZMANN_TEMPORAL_GROWTH_M6B1_P0_P1_PASS\n"
            << "M6B_MIXED_REDUCED_GROWTH=" <<
               mixed.reduced_growth_eigenvalue_m3_per_s << '\n'
            << "M6B_EIGEN_RESIDUAL=" << mixed.maximum_normalized_eigen_residual << '\n'
            << "M6B_INVERSE_ITERATIONS=" << mixed.inverse_iterations << '\n';
}
