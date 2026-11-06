#pragma once

#include "PhysicsBoltzmannTemporalGrowth.h"
#include "PhysicsBoltzmannEnergyMesh.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <vector>

namespace PhysicsBoltzmann
{
// Experimental Picard iteration: each inner eigen solve uses the previous
// normalized EEPF to construct a conservative positive *linear* growth Q.
// Only converged f/rates are self-consistent. The excitation operator remains
// the existing piecewise-constant M5 operator: P0-3 is NOT science-complete.
struct ReconstructedGrowthControls
{
  std::size_t maximum_updates = 12;
  std::size_t required_stable_updates = 2;
  double distribution_l1_limit = 1e-5;
  double rate_relative_limit = 1e-5;
  double mean_energy_relative_limit = 1e-5;
};

struct ReconstructedGrowthStep
{
  std::size_t update = 0;
  double distribution_l1_change = 0.0;
  double maximum_rate_relative_change = 0.0;
  double eigen_residual = 0.0;
  double mean_energy_relative_change = 0.0;
  bool stable = false;
};

struct ReconstructedGrowthResult
{
  TemporalGrowthResult solution;
  std::vector<ReconstructedGrowthStep> history;
  bool converged = false;
  std::string status = "HOLD_PICARD_MAX_UPDATES";
};

inline ReconstructedGrowthResult solveTemporalGrowthWithSubcellPicard(
    const ElasticInput & input,
    const std::vector<IonizationChannel> & ions,
    const std::vector<AttachmentChannel> & attachments,
    const std::vector<ExcitationChannel> & excitations = {},
    const ReconstructedGrowthControls & controls = {})
{
  if (controls.maximum_updates == 0 || controls.maximum_updates > 128 ||
      controls.required_stable_updates == 0 ||
      controls.required_stable_updates > controls.maximum_updates ||
      !(std::isfinite(controls.distribution_l1_limit) &&
        controls.distribution_l1_limit > 0.0 &&
        controls.distribution_l1_limit < 1.0) ||
      !(std::isfinite(controls.rate_relative_limit) &&
        controls.rate_relative_limit > 0.0 &&
        controls.rate_relative_limit < 1.0) ||
      !(std::isfinite(controls.mean_energy_relative_limit) &&
        controls.mean_energy_relative_limit > 0.0 &&
        controls.mean_energy_relative_limit < 1.0))
    throw std::invalid_argument("Boltzmann P0-3: invalid Picard controls");
  ReconstructedGrowthResult out;
  out.solution = solveElasticTemporalGrowth(input, ions, attachments, excitations);
  const auto edges = energyMeshEdges(input);
  std::size_t stable_updates = 0;
  for (std::size_t iteration = 0; iteration < controls.maximum_updates; ++iteration)
  {
    const auto & old = out.solution;
    auto next = solveElasticTemporalGrowth(
        input, ions, attachments, excitations,
        old.distribution.eepf_eV_minus_3_halves);
    double l1 = 0.0;
    for (std::size_t i = 0; i < input.cells; ++i)
    {
      const double mass = (2.0 / 3.0) *
          (std::pow(edges[i + 1], 1.5) - std::pow(edges[i], 1.5));
      l1 += mass * std::abs(next.distribution.eepf_eV_minus_3_halves[i] -
                            old.distribution.eepf_eV_minus_3_halves[i]);
    }
    double rate_change = 0.0;
    const auto compare = [&](const std::vector<double> & lhs,
                             const std::vector<double> & rhs)
    {
      if (lhs.size() != rhs.size())
        throw std::runtime_error("Boltzmann P0-3: changed process inventory");
      for (std::size_t i = 0; i < lhs.size(); ++i)
      {
        const double scale = std::max(1e-50, std::max(std::abs(lhs[i]), std::abs(rhs[i])));
        rate_change = std::max(rate_change, std::abs(lhs[i] - rhs[i]) / scale);
      }
    };
    compare(old.growth.ionization_rates_m3_per_s, next.growth.ionization_rates_m3_per_s);
    compare(old.growth.attachment_rates_m3_per_s, next.growth.attachment_rates_m3_per_s);
    const double energy_scale = std::max(1e-30,
        std::max(std::abs(old.distribution.mean_energy_eV),
                 std::abs(next.distribution.mean_energy_eV)));
    const double energy_change = std::abs(next.distribution.mean_energy_eV -
                                           old.distribution.mean_energy_eV) /
                                 energy_scale;
    const bool stable = l1 <= controls.distribution_l1_limit &&
                        rate_change <= controls.rate_relative_limit &&
                        energy_change <= controls.mean_energy_relative_limit &&
                        next.maximum_normalized_eigen_residual < 1e-8 &&
                        next.growth.operator_number_balance_relative_error < 1e-9;
    out.history.push_back({iteration + 1, l1, rate_change,
                           next.maximum_normalized_eigen_residual,
                           energy_change, stable});
    out.solution = std::move(next);
    stable_updates = stable ? stable_updates + 1 : 0;
    if (stable_updates >= controls.required_stable_updates)
    {
      out.converged = true;
      out.status = "CONVERGED_PICARD_GROWTH_ONLY_SCIENCE_HOLD";
      return out;
    }
  }
  return out;
}
} // namespace PhysicsBoltzmann
