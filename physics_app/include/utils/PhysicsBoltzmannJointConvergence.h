#pragma once

#include "PhysicsBoltzmannMeshRefinement.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace PhysicsBoltzmann
{
// DEVELOPMENT ONLY: require independent fixed-Emax mesh convergence at
// EVERY candidate ceiling. Neither a small tail nor stable coarse-grid
// rates can bypass an unconverged EEPF mesh. Each trial re-solves the actual
// M6b eigenproblem on at least two independently assembled FV meshes.
//
// This is a fail-closed two-dimensional numerical gate, NOT BOLSIG+ parity,
// NOT a replacement for the production Physics closure, and NOT P0-3.
struct JointGrowthControls
{
  EnergyCeilingControls ceiling;
  MeshRefinementControls refinement;
};

struct JointGrowthTrial
{
  double energy_ceiling_eV = 0.0;
  bool mesh_converged = false;
  std::string mesh_status;
  std::vector<MeshRefinementStep> mesh_history;
};

struct JointGrowthResult
{
  EnergyCeilingSelection ceiling;
  // Includes the failing mesh trial even if the ceiling controller has no
  // accepted sample for that Emax. Never erase evidence on resource HOLD.
  std::vector<JointGrowthTrial> trials;
};

inline JointGrowthResult solveTemporalGrowthWithJointConvergence(
    const ElasticInput & initial,
    const std::vector<IonizationChannel> & ionizations,
    const std::vector<AttachmentChannel> & attachments,
    const std::vector<ExcitationChannel> & excitations,
    const JointGrowthControls & c)
{
  validateEnergyCeilingControls(initial.max_energy_eV, c.ceiling);
  if (!initial.energy_cell_edges_eV.empty() ||
      c.refinement.mesh.maximum_cells > 256 ||
      (ionizations.empty() && attachments.empty()))
    throw std::invalid_argument(
        "Boltzmann joint convergence: unsupported mesh or collision inventory");

  // Reject truncated source data before running any eigenproblem. A table
  // must cover the largest possible independently proposed ceiling.
  const auto requireCoverage = [&](const std::vector<double> & energy) {
    if (energy.size() < 2 || !std::isfinite(energy.back()) ||
        energy.back() < c.ceiling.maximum_energy_eV)
      throw std::invalid_argument(
          "Boltzmann joint convergence: cross-section domain too short");
  };
  for (const auto & target : initial.targets)
    requireCoverage(target.energy_eV);
  for (const auto & channel : ionizations)
    requireCoverage(channel.energy_eV);
  for (const auto & channel : attachments)
    requireCoverage(channel.energy_eV);
  for (const auto & channel : excitations)
    requireCoverage(channel.energy_eV);

  EnergyCeilingControls ceiling = c.ceiling;
  const auto addThreshold = [&](double t) {
    if (!(std::isfinite(t) && t >= 0.0 &&
          t < initial.max_energy_eV))
      throw std::invalid_argument(
          "Boltzmann joint convergence: inactive initial threshold");
    if (t > 0.0)
      ceiling.required_thresholds_eV.push_back(t);
  };
  for (double t : c.ceiling.required_thresholds_eV)
    if (!(std::isfinite(t) && t > 0.0 && t < initial.max_energy_eV))
      throw std::invalid_argument(
          "Boltzmann joint convergence: required threshold inactive");
  for (const auto & channel : ionizations)
    addThreshold(channel.threshold_eV);
  for (const auto & channel : excitations)
    addThreshold(channel.threshold_eV);
  std::sort(ceiling.required_thresholds_eV.begin(),
            ceiling.required_thresholds_eV.end());
  ceiling.required_thresholds_eV.erase(
      std::unique(ceiling.required_thresholds_eV.begin(),
                  ceiling.required_thresholds_eV.end()),
      ceiling.required_thresholds_eV.end());

  JointGrowthResult out;
  out.ceiling = selectEnergyCeiling(
      initial.max_energy_eV, ceiling, [&](double emax) {
        ElasticInput fixed = initial;
        fixed.max_energy_eV = emax;
        // Preserve the initial nominal energy spacing when Emax expands.
        // Inner convergence is still independent and refines this base.
        const double scaled = std::ceil(
            static_cast<double>(c.refinement.initial_base_cells) *
            emax / initial.max_energy_eV);
        if (!(std::isfinite(scaled) && scaled >= 2.0 &&
              scaled <= static_cast<double>(c.refinement.maximum_base_cells)))
          throw EnergyCeilingHold("HOLD_JOINT_BASE_CELL_BUDGET");
        MeshRefinementControls refinement = c.refinement;
        refinement.initial_base_cells = static_cast<std::size_t>(scaled);
        const auto mesh = solveTemporalGrowthWithMeshRefinement(
            fixed, ionizations, attachments, excitations, refinement);
        JointGrowthTrial trial;
        trial.energy_ceiling_eV = emax;
        trial.mesh_converged = mesh.converged;
        trial.mesh_status = mesh.status;
        trial.mesh_history = mesh.history;
        out.trials.push_back(std::move(trial));
        if (!mesh.converged)
          throw EnergyCeilingHold("HOLD_JOINT_MESH_" + mesh.status);
        if (mesh.rates_m3_per_s.empty() ||
            mesh.distribution.energy_cell_edges_eV.empty())
          throw std::runtime_error(
              "Boltzmann joint convergence: converged mesh lacks rates/EEPF");
        return EnergyCeilingSample{
            mesh.distribution, mesh.rates_m3_per_s};
      });
  if (out.ceiling.converged)
  {
    // The status is deliberately science-HOLD even when both synthetic
    // numerical gates pass; no native reference has been checked.
    out.ceiling.status = "CONVERGED_JOINT_EMAX_MESH_SCIENCE_HOLD";
  }
  return out;
}
} // namespace PhysicsBoltzmann
