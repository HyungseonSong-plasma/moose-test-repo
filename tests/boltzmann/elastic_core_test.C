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

  // Identical cross-section targets must be mixture partition invariant.
  auto split = fixture(1000, 0.05);
  split.targets[0].mole_fraction = 0.3;
  auto duplicate = split.targets[0];
  duplicate.name = "synthetic-second-target";
  duplicate.mole_fraction = 0.7;
  split.targets.push_back(duplicate);
  const auto split_result = solveElasticSteadyState(split);
  if (relativeError(split_result.mean_energy_eV, result_low.mean_energy_eV) > 1e-12)
    throw std::runtime_error("identical-target mixture partition changed the EEPF");

  // Domain truncation control: extending epsilon_max should not materially
  // change a sufficiently decayed elastic distribution at the chosen E/N.
  auto expanded = fixture(2000, 0.2);
  expanded.max_energy_eV = 4.0;
  expanded.targets[0].energy_eV.back() = 4.0;
  const auto expanded_result = solveElasticSteadyState(expanded);
  if (relativeError(result_high.mean_energy_eV, expanded_result.mean_energy_eV) > 0.01)
    throw std::runtime_error("elastic EEPF failed epsilon_max refinement");


  // M2: one-way nonlocal excitation. This test deliberately uses an analytic
  // constant cross section, not a claimed real-gas data set.
  auto base = fixture(80, 0.2);
  ExcitationChannel channel;
  channel.name = "synthetic-excitation";
  channel.target_name = "synthetic-argon-like";
  channel.threshold_eV = 0.25;
  channel.energy_eV = {0.0, 2.0};
  channel.cross_section_m2 = {1.0e-20, 1.0e-20};

  const auto inel0 = solveExcitationSteadyState(base, {channel});
  base.cells = 160;
  const auto inel1 = solveExcitationSteadyState(base, {channel});
  base.cells = 320;
  const auto inel2 = solveExcitationSteadyState(base, {channel});
  const auto base_elastic = solveElasticSteadyState(base);
  if (!(inel0.distribution.mean_energy_eV > inel1.distribution.mean_energy_eV &&
        inel1.distribution.mean_energy_eV > inel2.distribution.mean_energy_eV &&
        inel2.distribution.mean_energy_eV < base_elastic.mean_energy_eV))
    throw std::runtime_error("nonlocal excitation energy-loss/refinement invariant failed");

  for (const auto & result : {inel0, inel1, inel2})
  {
    if (!(std::abs(result.distribution.normalization - 1.0) < 1e-12 &&
          result.maximum_normalized_equation_residual < 1e-8 &&
          result.maximum_collision_number_balance_error < 1e-9))
      throw std::runtime_error("excitation particle-number or residual invariant failed");
    if (!(result.rate_coefficients_m3_per_s.size() == 1 &&
          result.rate_coefficients_m3_per_s[0] > 0.0 &&
          relativeError(result.energy_loss_coefficients_eV_m3_per_s[0],
                        channel.threshold_eV * result.rate_coefficients_m3_per_s[0]) < 1e-14))
      throw std::runtime_error("excitation channel rate/energy-loss invariant failed");
    if (!std::isnan(result.distribution.maximum_normalized_flux_residual))
      throw std::runtime_error("inelastic energy flux must not be reported as zero residual");
  }

  // Independent channel-rate oracle: integral of epsilon * constant sigma
  // over every source cell above threshold, using *returned* normalized EEPF.
  double independent_rate = 0.0;
  const double h2 = 2.0 / static_cast<double>(base.cells);
  const double gamma = std::sqrt(2.0 * 1.602176634e-19 / 9.1093837139e-31);
  for (std::size_t i = 0; i < base.cells; ++i)
  {
    const double lo = std::max(static_cast<double>(i) * h2, channel.threshold_eV);
    const double hi = static_cast<double>(i + 1) * h2;
    if (hi > lo)
      independent_rate += gamma * 1e-20 * 0.5 * (hi * hi - lo * lo) *
                          inel2.distribution.eepf_eV_minus_3_halves[i];
  }
  if (relativeError(inel2.rate_coefficients_m3_per_s[0], independent_rate) > 1e-12)
    throw std::runtime_error("excitation rate disagrees with independent moment");

  // Off-grid transfer test: u/h is non-integral; recipients split between
  // adjacent cells. Piecewise-linear excitation cross sections must preserve
  // number even when the incoming/outgoing cells are not aligned.
  auto offgrid_input = fixture(125, 0.2);
  ExcitationChannel offgrid_channel = channel;
  offgrid_channel.threshold_eV = 0.27;
  offgrid_channel.energy_eV = {0.0, 1.0, 2.0};
  offgrid_channel.cross_section_m2 = {0.0, 1.0e-20, 2.0e-20};
  const auto shifted = solveExcitationSteadyState(offgrid_input, {offgrid_channel});
  if (!(shifted.maximum_collision_number_balance_error < 1e-9 &&
        shifted.maximum_normalized_equation_residual < 1e-8 &&
        shifted.rate_coefficients_m3_per_s[0] > 0.0 &&
        shifted.distribution.mean_energy_eV <
            solveElasticSteadyState(offgrid_input).mean_energy_eV))
    throw std::runtime_error("off-grid nonlocal excitation transfer failed conservation");

  // Independent kinetic energy-accounting oracle: the integrated SG
  // heating flux must approach threshold * excitation rate per target.
  // The collision operator uses exact overlap integrals, while cell-center
  // energy moments incur a controlled grid error (not an exact identity).
  const auto energyError = [](std::size_t ncells) -> double
  {
    auto test = fixture(ncells, 0.2);
    ExcitationChannel xc;
    xc.name = "energy-balance-oracle";
    xc.target_name = "synthetic-argon-like";
    xc.threshold_eV = 0.27;
    xc.energy_eV = {0.0, 1.0, 2.0};
    xc.cross_section_m2 = {0.0, 1e-20, 2e-20};
    const auto s = solveExcitationSteadyState(test, {xc});
    const auto & f = s.distribution.eepf_eV_minus_3_halves;
    const double h = 2.0 / static_cast<double>(ncells);
    const double gamma = std::sqrt(2.0 * 1.602176634e-19 / 9.1093837139e-31);
    const double theta = 1.380649e-23 * 300.0 / 1.602176634e-19;
    const double sigma_el = 5e-20;
    const double sigma_e = 2 * 1.37e-5 * sigma_el;
    double integrated_flux = 0.0;
    for (std::size_t i = 1; i < ncells; ++i)
    {
      const double e = static_cast<double>(i) * h;
      const double sigma_total = sigma_el + (e >= xc.threshold_eV ? 1e-20 * e : 0.0);
      const double W = -gamma * e * e * sigma_e;
      const double D = gamma * (0.2e-21 * 0.2e-21 * e / (3.0 * sigma_total) +
                                 theta * e * e * sigma_e);
      const double p = W * h / D;
      const auto bern = [](double z) {
        return std::abs(z) < 1e-4 ? 1.0 - z / 2.0 + z * z / 12.0 : z / std::expm1(z);
      };
      integrated_flux += D * (bern(-p) * f[i - 1] - bern(p) * f[i]);
    }
    const double excitation_loss =
        xc.threshold_eV * s.rate_coefficients_m3_per_s[0];
    if (!(excitation_loss > 0.0))
      throw std::runtime_error("zero inelastic energy loss in independent oracle");
    return std::abs(integrated_flux - excitation_loss) / excitation_loss;
  };
  const double energy_err_coarse = energyError(125);
  const double energy_err_fine = energyError(250);
  if (!(energy_err_fine < energy_err_coarse && energy_err_fine < 0.02))
    throw std::runtime_error("inelastic energy balance did not converge under grid refinement");

  // Zero-amplitude collision channel must recover the purely elastic M1
  // discrete equilibrium, not just the same qualitative trend.
  channel.cross_section_m2 = {0.0, 0.0};
  base.cells = 100;
  const auto no_excitation = solveExcitationSteadyState(base, {channel});
  const auto elastic_control = solveElasticSteadyState(base);
  if (relativeError(no_excitation.distribution.mean_energy_eV,
                    elastic_control.mean_energy_eV) > 1e-10)
    throw std::runtime_error("zero-excitation baseline parity failed");

  // P0 negative controls cover missing target, duplicate channel identity,
  // nonphysical threshold, insufficient energy domain and unsupported sizes.
  channel.cross_section_m2 = {1.0e-20, 1.0e-20};
  channel.target_name = "missing-target";
  reject([&] { (void)solveExcitationSteadyState(base, {channel}); });
  channel.target_name = "synthetic-argon-like";
  reject([&] { (void)solveExcitationSteadyState(base, {channel, channel}); });
  channel.threshold_eV = 2.0;
  reject([&] { (void)solveExcitationSteadyState(base, {channel}); });
  channel.threshold_eV = 0.25;
  channel.cross_section_m2[1] = -1.0;
  reject([&] { (void)solveExcitationSteadyState(base, {channel}); });
  channel.cross_section_m2[1] = 1.0e-20;
  reject([&] { (void)solveExcitationSteadyState(base, {}); });
  base.cells = 513;
  reject([&] { (void)solveExcitationSteadyState(base, {channel}); });

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

  std::cout << "BOLTZMANN_EXCITATION_M2_P0_P1_PASS\n" << "BOLTZMANN_ELASTIC_P0_P1_PASS\n"
            << "MAXWELL_REFINEMENT_ERRORS=" << err_c << ',' << err_f << ',' << err_ff << '\n'
            << "FIELD_MEAN_ENERGIES_EV=" << fine.mean_energy_eV << ','
            << result_low.mean_energy_eV << ',' << result_high.mean_energy_eV << '\n'
            << "EXCITATION_ENERGY_BALANCE_ERRORS=" << energy_err_coarse << ',' << energy_err_fine << '\n'
            << "MAX_NORMALIZED_FLUX_RESIDUAL=" << result_high.maximum_normalized_flux_residual
            << '\n';
}
