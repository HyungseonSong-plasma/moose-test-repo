#include "PhysicsBoltzmannTemporalGrowth.h"
#include <algorithm>
#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>

using namespace PhysicsBoltzmann;

namespace
{
ElasticInput sample(std::size_t n, bool upper = false)
{
  ElasticInput input;
  input.cells = n;
  input.max_energy_eV = 3.0;
  input.gas_temperature_K = 3000.0;
  input.reduced_field_Td = 0.2;
  input.targets.push_back({"synthetic_lower", upper ? 0.96 : 1.0, 1.37e-5,
                           {0.0, 3.0}, {5e-20, 5e-20}});
  if (upper)
    input.targets.push_back({"synthetic_upper", 0.04, 1.37e-5,
                             {0.0, 3.0}, {5e-20, 5e-20}});
  return input;
}
ExcitationChannel excite(bool reverse = false)
{
  ExcitationChannel ch{"synthetic_exc", "synthetic_lower", 0.4,
                       {0.0, 0.4, 0.41, 3.0}, {0.0, 0.0, 9e-21, 9e-21}};
  if (reverse)
  {
    ch.upper_state_target_name = "synthetic_upper";
    ch.upper_to_lower_weight_ratio = 2.0;
  }
  return ch;
}
IonizationChannel ion(double x)
{
  return {"synthetic_ion", "synthetic_lower", 0.7,
          {0.0, 0.7, 0.71, 3.0}, {0.0, 0.0, x, x}};
}
AttachmentChannel attach(double x)
{
  return {"synthetic_attach", "synthetic_lower",
          {0.0, 3.0}, {x, x}};
}
void inspect(const ElasticInput & input, const TemporalGrowthResult & r)
{
  const auto n = input.cells;
  const double h = input.max_energy_eV / n;
  double sum = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    const auto v = r.distribution.eepf_eV_minus_3_halves.at(i);
    if (!(std::isfinite(v) && v >= 0.0))
      throw std::runtime_error("M6b2 EEPF is negative/non-finite");
    sum += (2.0 / 3.0) * (std::pow((i+1)*h, 1.5)-std::pow(i*h, 1.5))*v;
  }
  if (!(std::abs(sum-1.0)<1e-9 &&
        r.maximum_normalized_eigen_residual < 1e-8 &&
        r.reduced_growth_eigenvalue_m3_per_s > 0.0 &&
        r.inverse_iterations > 0))
    throw std::runtime_error("M6b2 eigen mass, growth sign or true residual failed");
}
void reject(const std::function<void()> & fn)
{
  try { fn(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("M6b2 must reject invalid excitation channel");
}
} // namespace

int main()
{
  for (const std::size_t cells : {30u, 60u})
  {
    const auto input=sample(cells);
    const auto channel=excite();
    const auto m5 = solveExcitationSteadyState(input, {channel});
    const auto weak = solveElasticTemporalGrowth(input, {ion(1e-27)}, {}, {channel});
    inspect(input, weak);
    const double mdiff = std::abs(
        m5.distribution.mean_energy_eV - weak.distribution.mean_energy_eV);
    if (!(mdiff < 0.03))
      throw std::runtime_error("M6b2 does not reproduce M5 weak-growth EEPF");
    const auto strong = solveElasticTemporalGrowth(input, {ion(2e-20)},
                                                   {attach(1e-22)}, {channel});
    inspect(input, strong);
    const double rates =
        strong.growth.ionization_rates_m3_per_s[0] -
        strong.growth.attachment_rates_m3_per_s[0];
    if (!(std::abs(strong.reduced_growth_eigenvalue_m3_per_s - rates) <
          1e-10 * std::abs(rates)))
      throw std::runtime_error("M6b2 forward rate/eigenvalue closure failed");
  }

  // Explicit excited population and Klein-Rosseland inverse source are
  // inherited from the exact M5 conservative operator assembly.
  const auto rev_input = sample(50, true);
  const auto r = solveElasticTemporalGrowth(rev_input, {ion(1e-20)},
                                            {}, {excite(true)});
  inspect(rev_input, r);
  const auto oneway = solveElasticTemporalGrowth(rev_input, {ion(1e-20)},
                                                 {}, {excite(false)});
  inspect(rev_input, oneway);
  if (!(std::abs(r.distribution.mean_energy_eV -
                 oneway.distribution.mean_energy_eV) > 1e-9))
    throw std::runtime_error("M6b2 superelastic operator had no effect");

  auto bad = excite(true);
  bad.upper_to_lower_weight_ratio = 0.0;
  reject([&]{ (void)solveElasticTemporalGrowth(rev_input, {ion(1e-20)}, {}, {bad}); });
  bad = excite(true);
  bad.upper_state_target_name = "absent";
  reject([&]{ (void)solveElasticTemporalGrowth(rev_input, {ion(1e-20)}, {}, {bad}); });

  std::cout << "BOLTZMANN_TEMPORAL_GROWTH_M6B2_P0_P1_PASS\n"
            << "M6B2_EIGEN_RESIDUAL=" << r.maximum_normalized_eigen_residual << '\n'
            << "M6B2_REDUCED_GROWTH=" << r.reduced_growth_eigenvalue_m3_per_s << '\n';
}
