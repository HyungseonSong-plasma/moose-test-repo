#pragma once

#include "PhysicsBoltzmannEnergyCeiling.h"
#include "PhysicsBoltzmannTemporalGrowth.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

namespace PhysicsBoltzmann
{
// P0-1 DEVELOPMENT: unlike the elastic-only adapter, this adapter reassembles
// the actual temporal-growth eigenproblem and all inelastic collision channels
// at EACH proposed ceiling. This is not a BOLSIG+ automatic-grid equivalent.
//
// The dense M6b reference is limited to 256 cells. A ceiling requiring more
// cells returns an explicit HOLD rather than silently coarsening the mesh.
// A source table that cannot cover the requested maximum is rejected up front:
// constant extrapolation of cross sections would otherwise masquerade as
// independently converged physics.
inline EnergyCeilingSelection solveTemporalGrowthWithAutomaticCeiling(
    const ElasticInput & initial,
    const std::vector<IonizationChannel> & ionizations,
    const std::vector<AttachmentChannel> & attachments,
    const std::vector<ExcitationChannel> & excitations,
    const EnergyCeilingControls & requested)
{
  validateEnergyCeilingControls(initial.max_energy_eV, requested);
  if (!initial.energy_cell_edges_eV.empty() ||
      initial.cells < 2 || initial.cells > 256)
    throw std::invalid_argument(
        "Boltzmann Emax growth: dense reference requires a uniform [2,256] cell initial mesh");
  if (ionizations.empty() && attachments.empty())
    throw std::invalid_argument(
        "Boltzmann Emax growth: at least one particle-changing channel required");

  const auto requireCoverage = [&](const std::vector<double> & energy) {
    if (energy.size() < 2 || !std::isfinite(energy.back()) ||
        energy.back() < requested.maximum_energy_eV)
      throw std::invalid_argument(
          "Boltzmann Emax growth: collision table does not cover requested maximum");
  };
  for (const auto & target : initial.targets)
    requireCoverage(target.energy_eV);
  for (const auto & channel : ionizations)
    requireCoverage(channel.energy_eV);
  for (const auto & channel : attachments)
    requireCoverage(channel.energy_eV);
  for (const auto & channel : excitations)
    requireCoverage(channel.energy_eV);

  EnergyCeilingControls controls = requested;
  // The actual M6 collision inventory is fixed throughout the sweep. Every
  // represented inelastic threshold must be below the initial Emax, so no
  // dormant channel is silently switched on partway through convergence.
  const auto addThreshold = [&](double threshold) {
    if (!(std::isfinite(threshold) && threshold >= 0.0 &&
          threshold < initial.max_energy_eV))
      throw std::invalid_argument(
          "Boltzmann Emax growth: represented threshold not active at initial ceiling");
    controls.required_thresholds_eV.push_back(threshold);
  };
  for (const auto & channel : ionizations)
    addThreshold(channel.threshold_eV);
  for (const auto & channel : excitations)
    addThreshold(channel.threshold_eV);

  const double dense_limit = initial.max_energy_eV *
      (256.0 / static_cast<double>(initial.cells));
  const bool dense_capped = dense_limit < requested.maximum_energy_eV;
  controls.maximum_energy_eV = dense_capped ?
      std::max(initial.max_energy_eV, std::nextafter(dense_limit, 0.0)) :
      requested.maximum_energy_eV;

  auto selected = selectEnergyCeiling(initial.max_energy_eV, controls,
      [&](double emax) {
        ElasticInput current = initial;
        current.max_energy_eV = emax;
        const double cells = std::ceil(
            static_cast<double>(initial.cells) * emax / initial.max_energy_eV);
        if (!(std::isfinite(cells) && cells >= 2.0 && cells <= 256.0))
          throw std::runtime_error(
              "Boltzmann Emax growth: dense reference cell budget exceeded");
        current.cells = static_cast<std::size_t>(cells);

        // Do not reuse a frozen EEPF or stale gain/loss matrix.
        const auto eigen = solveElasticTemporalGrowth(
            current, ionizations, attachments, excitations);
        if (!(std::isfinite(eigen.maximum_normalized_eigen_residual) &&
              eigen.maximum_normalized_eigen_residual < 1e-8))
          throw std::runtime_error(
              "Boltzmann Emax growth: invalid self-consistent eigen residual");

        EnergyCeilingSample sample;
        sample.distribution = eigen.distribution;
        sample.rates_m3_per_s = eigen.growth.ionization_rates_m3_per_s;
        sample.rates_m3_per_s.insert(sample.rates_m3_per_s.end(),
            eigen.growth.attachment_rates_m3_per_s.begin(),
            eigen.growth.attachment_rates_m3_per_s.end());
        if (!excitations.empty())
        {
          const auto moments = evaluateExcitationRatesOnEepf(
              current, sample.distribution, excitations);
          sample.rates_m3_per_s.insert(sample.rates_m3_per_s.end(),
              moments.forward_rates_m3_per_s.begin(),
              moments.forward_rates_m3_per_s.end());
          sample.rates_m3_per_s.insert(sample.rates_m3_per_s.end(),
              moments.reverse_rates_m3_per_s.begin(),
              moments.reverse_rates_m3_per_s.end());
        }
        return sample;
      });
  if (dense_capped && !selected.converged &&
      selected.status == "HOLD_MAX_ENERGY_LIMIT")
    selected.status = "HOLD_DENSE_REFERENCE_CELL_LIMIT";
  return selected;
}
} // namespace PhysicsBoltzmann
