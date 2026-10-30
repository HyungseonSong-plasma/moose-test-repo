#include "PhysicsBoltzmannTransport.h"

#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>

using namespace PhysicsBoltzmann;

namespace
{
ElasticInput fixture(std::size_t cells, double max_energy = 3.0)
{
  ElasticInput in;
  in.max_energy_eV = max_energy;
  in.cells = cells;
  in.gas_temperature_K = 3000.0;
  in.reduced_field_Td = 0.0;
  in.targets.push_back({"synthetic_constant_sigma", 1.0, 1.37e-5,
                        {0.0, 3.0}, {5e-20, 5e-20}});
  return in;
}

void reject(const std::function<void()> & fn)
{
  try { fn(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("Boltzmann M7: malformed input was not rejected");
}

double relative(double a, double b)
{
  return std::abs(a - b) / std::abs(b);
}
} // namespace

int main()
{
  constexpr double theta = 1.380649e-23 * 3000.0 / 1.602176634e-19;
  const auto coarse = fixture(200);
  const auto fine = fixture(800);
  const auto f_c = solveElasticSteadyState(coarse);
  const auto f_f = solveElasticSteadyState(fine);
  const auto c = evaluateElasticTransportMoments(coarse, f_c);
  const auto f = evaluateElasticTransportMoments(fine, f_f);
  const double ratio_c = c.reduced_diffusion_N_per_m_s /
                         c.reduced_mobility_N_per_m_V_s;
  const double ratio_f = f.reduced_diffusion_N_per_m_s /
                         f.reduced_mobility_N_per_m_V_s;
  if (!(relative(ratio_c, theta) < 0.01 &&
        relative(ratio_f, theta) < 0.01 &&
        std::abs(ratio_f - ratio_c) < 0.01 * theta))
    throw std::runtime_error("Boltzmann M7: constant-sigma Maxwellian D/mu limit failed");

  // For an energy-independent *cross section*, the collision frequency is
  // energy-dependent. Electron-energy transport ratios approach 4/3 in
  // the Maxwellian limit, NOT the often assumed 5/3 constant-frequency
  // closure. Both coefficients are separately integrated from the EEPF.
  const double m_ratio =
      f.reduced_energy_mobility_N_per_m_V_s / f.reduced_mobility_N_per_m_V_s;
  const double d_ratio =
      f.reduced_energy_diffusion_N_per_m_s / f.reduced_diffusion_N_per_m_s;
  if (!(std::abs(m_ratio - 4.0 / 3.0) < 0.015 &&
        std::abs(d_ratio - 4.0 / 3.0) < 0.015 &&
        std::abs(d_ratio - 5.0 / 3.0) > 0.25))
    throw std::runtime_error("Boltzmann M7: energy transport incorrectly uses 5/3 closure");

  // Positivity and normalization controls for an explicitly non-Maxwellian,
  // monotonically decreasing EEPF; no Einstein approximation is injected.
  ElasticResult non_maxwell = f_f;
  const double h = fine.max_energy_eV / fine.cells;
  double area = 0.0, moment = 0.0;
  for (std::size_t i = 0; i < fine.cells; ++i)
  {
    const double e = non_maxwell.energy_eV[i];
    non_maxwell.eepf_eV_minus_3_halves[i] *= 1.0 + 0.7 * e;
    const double lo = i * h, hi = (i + 1) * h;
    area += non_maxwell.eepf_eV_minus_3_halves[i] *
            (2.0 / 3.0) * (std::pow(hi, 1.5) - std::pow(lo, 1.5));
    moment += non_maxwell.eepf_eV_minus_3_halves[i] *
              (2.0 / 5.0) * (std::pow(hi, 2.5) - std::pow(lo, 2.5));
  }
  for (auto & v : non_maxwell.eepf_eV_minus_3_halves)
    v /= area;
  non_maxwell.mean_energy_eV = moment / area;
  const auto nontherm = evaluateElasticTransportMoments(fine, non_maxwell);
  if (!(nontherm.reduced_mobility_N_per_m_V_s > 0.0 &&
        nontherm.reduced_diffusion_N_per_m_s > 0.0 &&
        nontherm.reduced_energy_diffusion_N_per_m_s > 0.0 &&
        nontherm.high_energy_tail_ratio < 1e-3))
    throw std::runtime_error("Boltzmann M7: non-Maxwellian EEPF transport failed");

  auto truncated = fixture(100, 0.2);
  auto truncated_distribution = solveElasticSteadyState(truncated);
  reject([&] { (void)evaluateElasticTransportMoments(truncated, truncated_distribution); });
  auto malformed = fine;
  malformed.targets[0].mole_fraction = 0.5;
  reject([&] { (void)evaluateElasticTransportMoments(malformed, f_f); });
  auto damaged = f_f;
  damaged.eepf_eV_minus_3_halves[0] *= 1.5;
  reject([&] { (void)evaluateElasticTransportMoments(fine, damaged); });

  std::cout << "BOLTZMANN_TRANSPORT_M7A_P0_P1_PASS\n"
            << "M7_REDUCED_MOBILITY=" << f.reduced_mobility_N_per_m_V_s << '\n'
            << "M7_REDUCED_DIFFUSION=" << f.reduced_diffusion_N_per_m_s << '\n'
            << "M7_ENERGY_DIFFUSION_TO_DIFFUSION=" << d_ratio << '\n';
}
