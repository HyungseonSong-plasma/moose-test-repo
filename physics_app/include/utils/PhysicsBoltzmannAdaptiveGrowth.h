#pragma once

#include "PhysicsBoltzmannGrowthCeiling.h"
#include "PhysicsBoltzmannThresholdMesh.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <vector>

namespace PhysicsBoltzmann
{
// P0-1/P0-2 DEVELOPMENT: at EACH candidate Emax, build a fresh threshold-
// aligned nonuniform finite-volume grid and solve the actual M6b coupled
// temporal-growth eigenproblem. Rates are recomputed on the new eigen-EEPF.
// Neither the grid nor the ceiling is informed by native BOLSIG+ output.
//
// This is not P0-3 subcell EEPF reconstruction or production-scale sparse
// eigensolving. Exceeding the 256-cell dense budget is an explicit HOLD.
inline EnergyCeilingSelection solveTemporalGrowthWithAdaptiveMesh(
    const ElasticInput & initial,
    const std::vector<IonizationChannel> & ionizations,
    const std::vector<AttachmentChannel> & attachments,
    const std::vector<ExcitationChannel> & excitations,
    const EnergyCeilingControls & requested,
    const ThresholdMeshControls & mesh_controls = {})
{
  validateEnergyCeilingControls(initial.max_energy_eV, requested);
  if (!initial.energy_cell_edges_eV.empty() || initial.cells < 2 ||
      initial.cells > 256 || mesh_controls.maximum_cells > 256)
    throw std::invalid_argument(
        "Boltzmann adaptive growth: initial mesh or dense cell budget invalid");
  if (ionizations.empty() && attachments.empty())
    throw std::invalid_argument(
        "Boltzmann adaptive growth: particle-changing channel required");

  // Never silently extrapolate an underspecified source table to a ceiling
  // at which a channel may become active.
  const auto requireCoverage = [&](const std::vector<double> & energy) {
    if (energy.size() < 2 || !std::isfinite(energy.back()) ||
        energy.back() < requested.maximum_energy_eV)
      throw std::invalid_argument(
          "Boltzmann adaptive growth: collision table does not cover maximum Emax");
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
  std::vector<double> thresholds = requested.required_thresholds_eV;
  const auto addThreshold = [&](double threshold) {
    if (!(std::isfinite(threshold) && threshold >= 0.0 &&
          threshold < initial.max_energy_eV))
      throw std::invalid_argument(
          "Boltzmann adaptive growth: inactive or invalid threshold");
    if (threshold > 0.0)
      thresholds.push_back(threshold);
  };
  for (double threshold : requested.required_thresholds_eV)
    if (!(std::isfinite(threshold) && threshold > 0.0 &&
          threshold < initial.max_energy_eV))
      throw std::invalid_argument(
          "Boltzmann adaptive growth: required threshold not active");
  for (const auto & channel : ionizations)
    addThreshold(channel.threshold_eV);
  for (const auto & channel : excitations)
    addThreshold(channel.threshold_eV);
  std::sort(thresholds.begin(), thresholds.end());
  thresholds.erase(std::unique(thresholds.begin(), thresholds.end()),
                   thresholds.end());
  controls.required_thresholds_eV = thresholds;

  return selectEnergyCeiling(initial.max_energy_eV, controls,
      [&](double emax) {
        const double base = std::ceil(
            static_cast<double>(initial.cells) * emax / initial.max_energy_eV);
        if (!(std::isfinite(base) && base >= 2.0 &&
              base <= static_cast<double>(mesh_controls.maximum_cells)))
          throw EnergyCeilingHold("HOLD_DENSE_REFERENCE_CELL_LIMIT");

        ElasticInput current = initial;
        current.max_energy_eV = emax;
        current.cells = static_cast<std::size_t>(base);
        try
        {
          current = withThresholdAwareMesh(current, thresholds, mesh_controls);
        }
        catch (const std::runtime_error & error)
        {
          // Translate only the known, expected mesh-budget stop. All other
          // geometry/numerical errors remain hard failures, not false PASS.
          if (std::string(error.what()).find("HOLD_DENSE_REFERENCE_CELL_LIMIT") ==
              std::string::npos)
            throw;
          throw EnergyCeilingHold("HOLD_DENSE_REFERENCE_CELL_LIMIT");
        }

        const auto eigen = solveElasticTemporalGrowth(
            current, ionizations, attachments, excitations);
        if (!(std::isfinite(eigen.maximum_normalized_eigen_residual) &&
              eigen.maximum_normalized_eigen_residual < 1e-8))
          throw std::runtime_error(
              "Boltzmann adaptive growth: nonconverged coupled eigenproblem");

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
}
} // namespace PhysicsBoltzmann
