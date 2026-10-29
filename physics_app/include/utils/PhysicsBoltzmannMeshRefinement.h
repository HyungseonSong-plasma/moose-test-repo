#pragma once

#include "PhysicsBoltzmannGrowthCeiling.h"
#include "PhysicsBoltzmannThresholdMesh.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace PhysicsBoltzmann
{
// P0-2 DEVELOPMENT: independent fixed-Emax mesh convergence gate.
// Do not confuse Emax convergence with grid convergence. Each refinement
// assembles and solves a NEW M6b eigenproblem and recomputes ALL rates.
// Synthetic CI evidence is not native BOLSIG+ parity.
struct MeshRefinementControls
{
  std::size_t initial_base_cells = 16;
  std::size_t maximum_base_cells = 160;
  std::size_t maximum_refinements = 5;
  std::size_t required_stable_refinements = 2;
  double base_growth_factor = 1.5;
  double mean_relative_limit = 1e-3;
  double rate_relative_limit = 1e-2;
  double distribution_l1_limit = 1e-2;
  ThresholdMeshControls mesh;
};

struct MeshRefinementStep
{
  std::size_t base_cells = 0;
  std::size_t actual_cells = 0;
  double mean_energy_eV = 0.0;
  double eigen_residual = 0.0;
  double collision_number_balance_error = 0.0;
  double mean_relative_change = std::numeric_limits<double>::infinity();
  double maximum_rate_relative_change = std::numeric_limits<double>::infinity();
  double distribution_l1_change = std::numeric_limits<double>::infinity();
  bool stable = false;
};

struct MeshRefinementResult
{
  bool converged = false;
  std::string status = "HOLD_NOT_RUN";
  ElasticResult distribution;
  // Rates corresponding to the last actually re-solved EEPF, in the same
  // ionization/attachment/forward/reverse inventory as each refinement.
  // This allows the outer Emax gate to compare genuinely mesh-refined rates.
  std::vector<double> rates_m3_per_s;
  std::vector<MeshRefinementStep> history;
};

// Conservative, exact-in-cell L1 comparison for piecewise constant EEPFs
// on DIFFERENT meshes: integral sqrt(E)*abs(f_old-f_new) dE.
// Normalized distributions have 0 <= L1 <= 2 (up to roundoff).
inline double fvEepfL1Distance(const ElasticResult & a,
                               const ElasticResult & b)
{
  const auto & ae = a.energy_cell_edges_eV;
  const auto & be = b.energy_cell_edges_eV;
  const auto & af = a.eepf_eV_minus_3_halves;
  const auto & bf = b.eepf_eV_minus_3_halves;
  if (af.empty() || bf.empty() || ae.size() != af.size() + 1 ||
      be.size() != bf.size() + 1 || ae.front() != 0.0 ||
      be.front() != 0.0 || ae.back() != be.back())
    throw std::invalid_argument("Boltzmann mesh convergence: incompatible EEPF domains");
  double norm_a = 0.0, norm_b = 0.0, distance = 0.0;
  for (std::size_t k = 0; k < af.size(); ++k)
  {
    if (!(std::isfinite(af[k]) && af[k] >= 0.0 &&
          std::isfinite(ae[k]) && std::isfinite(ae[k + 1]) &&
          ae[k + 1] > ae[k]))
      throw std::invalid_argument("Boltzmann mesh convergence: invalid first EEPF");
    norm_a += af[k] * (2.0 / 3.0) *
        (std::pow(ae[k + 1], 1.5) - std::pow(ae[k], 1.5));
  }
  for (std::size_t k = 0; k < bf.size(); ++k)
  {
    if (!(std::isfinite(bf[k]) && bf[k] >= 0.0 &&
          std::isfinite(be[k]) && std::isfinite(be[k + 1]) &&
          be[k + 1] > be[k]))
      throw std::invalid_argument("Boltzmann mesh convergence: invalid second EEPF");
    norm_b += bf[k] * (2.0 / 3.0) *
        (std::pow(be[k + 1], 1.5) - std::pow(be[k], 1.5));
  }
  if (std::abs(norm_a - 1.0) > 1e-8 || std::abs(norm_b - 1.0) > 1e-8)
    throw std::invalid_argument("Boltzmann mesh convergence: unnormalized EEPF");
  std::size_t i = 0, j = 0;
  while (i < af.size() && j < bf.size())
  {
    const double lo = std::max(ae[i], be[j]);
    const double hi = std::min(ae[i + 1], be[j + 1]);
    if (hi > lo)
      distance += (2.0 / 3.0) *
          (std::pow(hi, 1.5) - std::pow(lo, 1.5)) *
          std::abs(af[i] - bf[j]);
    const double ai = ae[i + 1], bj = be[j + 1];
    if (ai <= bj)
      ++i;
    if (bj <= ai)
      ++j;
  }
  if (!(std::isfinite(distance) && distance >= 0.0 && distance <= 2.0 + 1e-8))
    throw std::runtime_error("Boltzmann mesh convergence: invalid L1 distance");
  return distance;
}

inline MeshRefinementResult solveTemporalGrowthWithMeshRefinement(
    const ElasticInput & fixed,
    const std::vector<IonizationChannel> & ionizations,
    const std::vector<AttachmentChannel> & attachments,
    const std::vector<ExcitationChannel> & excitations,
    const MeshRefinementControls & c = {})
{
  if (!(std::isfinite(fixed.max_energy_eV) && fixed.max_energy_eV > 0.0 &&
        fixed.energy_cell_edges_eV.empty() &&
        c.initial_base_cells >= 2 &&
        c.maximum_base_cells >= c.initial_base_cells &&
        c.maximum_refinements >= c.required_stable_refinements &&
        c.required_stable_refinements >= 1 &&
        std::isfinite(c.base_growth_factor) && c.base_growth_factor > 1.0 &&
        std::isfinite(c.mean_relative_limit) && c.mean_relative_limit > 0.0 &&
        std::isfinite(c.rate_relative_limit) && c.rate_relative_limit > 0.0 &&
        std::isfinite(c.distribution_l1_limit) &&
        c.distribution_l1_limit > 0.0 && c.distribution_l1_limit <= 2.0 &&
        c.mesh.maximum_cells <= 256 &&
        (ionizations.size() + attachments.size()) > 0))
    throw std::invalid_argument("Boltzmann mesh convergence: invalid controls");
  std::vector<double> thresholds;
  const auto add = [&](double t) {
    if (!(std::isfinite(t) && t >= 0.0 && t < fixed.max_energy_eV))
      throw std::invalid_argument("Boltzmann mesh convergence: inactive threshold");
    if (t > 0.0)
      thresholds.push_back(t);
  };
  for (const auto & ch : ionizations)
    add(ch.threshold_eV);
  for (const auto & ch : excitations)
    add(ch.threshold_eV);
  std::sort(thresholds.begin(), thresholds.end());
  thresholds.erase(std::unique(thresholds.begin(), thresholds.end()),
                   thresholds.end());

  MeshRefinementResult out;
  ElasticResult previous;
  std::vector<double> previous_rates;
  bool has_previous = false;
  std::size_t stable_count = 0;
  std::size_t base_cells = c.initial_base_cells;
  for (std::size_t iteration = 0; iteration <= c.maximum_refinements; ++iteration)
  {
    if (base_cells > c.maximum_base_cells)
    {
      out.status = "HOLD_MAXIMUM_BASE_CELLS";
      return out;
    }
    ElasticInput input = fixed;
    input.cells = base_cells;
    try
    {
      input = withThresholdAwareMesh(input, thresholds, c.mesh);
    }
    catch (const std::runtime_error & error)
    {
      if (std::string(error.what()).find("HOLD_DENSE_REFERENCE_CELL_LIMIT") ==
          std::string::npos)
        throw;
      out.status = "HOLD_DENSE_REFERENCE_CELL_LIMIT";
      return out;
    }
    const auto eigen = solveElasticTemporalGrowth(
        input, ionizations, attachments, excitations);
    if (!(std::isfinite(eigen.maximum_normalized_eigen_residual) &&
          eigen.maximum_normalized_eigen_residual < 1e-8 &&
          std::isfinite(eigen.growth.operator_number_balance_relative_error) &&
          eigen.growth.operator_number_balance_relative_error < 1e-9))
      throw std::runtime_error("Boltzmann mesh convergence: eigen or conservation failure");

    std::vector<double> rates = eigen.growth.ionization_rates_m3_per_s;
    rates.insert(rates.end(), eigen.growth.attachment_rates_m3_per_s.begin(),
                 eigen.growth.attachment_rates_m3_per_s.end());
    if (!excitations.empty())
    {
      const auto moments = evaluateExcitationRatesOnEepf(
          input, eigen.distribution, excitations);
      rates.insert(rates.end(), moments.forward_rates_m3_per_s.begin(),
                   moments.forward_rates_m3_per_s.end());
      rates.insert(rates.end(), moments.reverse_rates_m3_per_s.begin(),
                   moments.reverse_rates_m3_per_s.end());
    }
    if (rates.empty())
      throw std::runtime_error("Boltzmann mesh convergence: no monitored rates");
    for (double rate : rates)
      if (!(std::isfinite(rate) && rate >= 0.0))
        throw std::runtime_error("Boltzmann mesh convergence: nonphysical rate");

    MeshRefinementStep step;
    step.base_cells = base_cells;
    step.actual_cells = input.cells;
    step.mean_energy_eV = eigen.distribution.mean_energy_eV;
    step.eigen_residual = eigen.maximum_normalized_eigen_residual;
    step.collision_number_balance_error =
        eigen.growth.operator_number_balance_relative_error;
    if (has_previous)
    {
      if (rates.size() != previous_rates.size())
        throw std::runtime_error("Boltzmann mesh convergence: rate inventory changed");
      step.mean_relative_change =
          std::abs(step.mean_energy_eV - previous.mean_energy_eV) /
          std::max(step.mean_energy_eV, previous.mean_energy_eV);
      step.distribution_l1_change =
          fvEepfL1Distance(previous, eigen.distribution);
      step.maximum_rate_relative_change = 0.0;
      for (std::size_t i = 0; i < rates.size(); ++i)
      {
        const double scale = std::max(rates[i], previous_rates[i]);
        const double relative = scale == 0.0 ? 0.0 :
            std::abs(rates[i] - previous_rates[i]) / scale;
        step.maximum_rate_relative_change =
            std::max(step.maximum_rate_relative_change, relative);
      }
      step.stable =
          step.mean_relative_change <= c.mean_relative_limit &&
          step.maximum_rate_relative_change <= c.rate_relative_limit &&
          step.distribution_l1_change <= c.distribution_l1_limit;
      stable_count = step.stable ? stable_count + 1 : 0;
    }
    out.history.push_back(step);
    out.distribution = eigen.distribution;
    out.rates_m3_per_s = rates;
    if (stable_count >= c.required_stable_refinements)
    {
      out.converged = true;
      out.status = "CONVERGED_FIXED_EMAX_MESH_SCIENCE_HOLD";
      return out;
    }
    if (iteration == c.maximum_refinements)
    {
      out.status = "HOLD_MAX_REFINEMENTS";
      return out;
    }
    previous = eigen.distribution;
    previous_rates = std::move(rates);
    has_previous = true;
    const double grown = std::ceil(
        static_cast<double>(base_cells) * c.base_growth_factor);
    if (!(std::isfinite(grown) && grown > static_cast<double>(base_cells) &&
          grown <= static_cast<double>(std::numeric_limits<std::size_t>::max())))
      throw std::invalid_argument("Boltzmann mesh convergence: invalid base growth");
    base_cells = static_cast<std::size_t>(grown);
  }
  return out;
}
} // namespace PhysicsBoltzmann
