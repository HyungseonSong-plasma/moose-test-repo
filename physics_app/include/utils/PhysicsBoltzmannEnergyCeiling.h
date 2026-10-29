#pragma once

#include "PhysicsBoltzmannElasticSolver.h"

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
// P0-1 experimental, source-independent energy-ceiling convergence controller.
// The caller MUST re-solve the actual physics at every Emax. This algorithm
// never consumes a native BOLSIG+ Emax, and does not assert physical parity.
// The rates callback must use the *new* distribution, not cached old rates.
struct EnergyCeilingControls
{
  double maximum_energy_eV = 200.0;
  double expansion_factor = 1.5;
  double tail_window_fraction = 0.1;
  double tail_mass_limit = 1e-7;
  double tail_energy_limit = 1e-6;
  double moment_relative_limit = 1e-3;
  double rate_relative_limit = 1e-2;
  std::size_t max_expansions = 12;
  std::size_t required_stable_expansions = 2;
  // Only explicitly required active thresholds belong here: including every
  // dormant high-energy database threshold would force an unphysical ceiling.
  std::vector<double> required_thresholds_eV;
  double threshold_guard_cells = 2.0;
};

struct EnergyCeilingSample
{
  ElasticResult distribution;
  // Optional reaction coefficients, calculated on this distribution.
  // An empty vector is explicitly recorded as "rates not monitored".
  std::vector<double> rates_m3_per_s;
};

struct EnergyCeilingIteration
{
  double energy_ceiling_eV = 0.0;
  std::size_t cells = 0;
  double mean_energy_eV = 0.0;
  double tail_number_fraction = 0.0;
  double tail_energy_fraction = 0.0;
  double mean_relative_change = std::numeric_limits<double>::infinity();
  double maximum_rate_relative_change = std::numeric_limits<double>::infinity();
  bool rates_monitored = false;
  bool thresholds_monitored = false;
  bool threshold_resolved = false;
  bool stable = false;
};

struct EnergyCeilingSelection
{
  bool converged = false;
  std::string status = "HOLD_NOT_RUN";
  ElasticResult distribution;
  std::vector<EnergyCeilingIteration> history;
};

// Independent conservative finite-volume moments. A tail integral starts at
// (1-tail_window_fraction)*Emax and clips the straddling cell exactly.
inline EnergyCeilingIteration inspectEnergyCeilingSample(
    const EnergyCeilingSample & sample, double emax,
    const EnergyCeilingControls & controls)
{
  const auto & d = sample.distribution;
  const auto & edges = d.energy_cell_edges_eV;
  const auto & f = d.eepf_eV_minus_3_halves;
  if (!(std::isfinite(emax) && emax > 0.0) || f.size() < 2 ||
      edges.size() != f.size() + 1 || edges.front() != 0.0 ||
      std::abs(edges.back() - emax) > 1e-12 * emax ||
      !(std::isfinite(d.mean_energy_eV) && d.mean_energy_eV > 0.0))
    throw std::invalid_argument("Boltzmann Emax: invalid distribution geometry");

  double mass = 0.0, energy = 0.0, tail_mass = 0.0, tail_energy = 0.0;
  const double tail_start = emax * (1.0 - controls.tail_window_fraction);
  for (std::size_t i = 0; i < f.size(); ++i)
  {
    const double l = edges[i], r = edges[i + 1], v = f[i];
    if (!(std::isfinite(l) && std::isfinite(r) && r > l &&
          std::isfinite(v) && v >= 0.0))
      throw std::invalid_argument("Boltzmann Emax: nonphysical FV cell or EEPF");
    const auto number_weight = [](double a, double b) {
      return (2.0 / 3.0) * (std::pow(b, 1.5) - std::pow(a, 1.5));
    };
    const auto energy_weight = [](double a, double b) {
      return (2.0 / 5.0) * (std::pow(b, 2.5) - std::pow(a, 2.5));
    };
    mass += v * number_weight(l, r);
    energy += v * energy_weight(l, r);
    if (r > tail_start)
    {
      const double a = std::max(l, tail_start);
      tail_mass += v * number_weight(a, r);
      tail_energy += v * energy_weight(a, r);
    }
  }
  if (!(std::isfinite(mass) && std::abs(mass - 1.0) <= 1e-8 &&
        std::isfinite(energy) && energy > 0.0 &&
        std::abs(energy - d.mean_energy_eV) <=
            1e-8 * std::max(energy, d.mean_energy_eV)))
    throw std::invalid_argument("Boltzmann Emax: FV normalization or mean-energy mismatch");
  for (double rate : sample.rates_m3_per_s)
    if (!std::isfinite(rate))
      throw std::invalid_argument("Boltzmann Emax: nonfinite monitored rate");

  EnergyCeilingIteration item;
  item.energy_ceiling_eV = emax;
  item.cells = f.size();
  item.mean_energy_eV = energy;
  item.tail_number_fraction = tail_mass / mass;
  item.tail_energy_fraction = tail_energy / energy;
  item.rates_monitored = !sample.rates_m3_per_s.empty();
  item.thresholds_monitored = !controls.required_thresholds_eV.empty();
  item.threshold_resolved = true;
  const double last_width = edges.back() - edges[edges.size() - 2];
  for (double threshold : controls.required_thresholds_eV)
    if (!(std::isfinite(threshold) && threshold >= 0.0 &&
          emax > threshold + controls.threshold_guard_cells * last_width))
      item.threshold_resolved = false;
  return item;
}

inline void validateEnergyCeilingControls(double initial,
                                          const EnergyCeilingControls & c)
{
  if (!(std::isfinite(initial) && initial > 0.0 &&
        std::isfinite(c.maximum_energy_eV) && c.maximum_energy_eV >= initial &&
        std::isfinite(c.expansion_factor) && c.expansion_factor > 1.0 &&
        std::isfinite(c.tail_window_fraction) && c.tail_window_fraction > 0.0 &&
        c.tail_window_fraction < 1.0 &&
        std::isfinite(c.tail_mass_limit) && c.tail_mass_limit > 0.0 &&
        c.tail_mass_limit < 1.0 &&
        std::isfinite(c.tail_energy_limit) && c.tail_energy_limit > 0.0 &&
        c.tail_energy_limit < 1.0 &&
        std::isfinite(c.moment_relative_limit) && c.moment_relative_limit > 0.0 &&
        std::isfinite(c.rate_relative_limit) && c.rate_relative_limit > 0.0 &&
        std::isfinite(c.threshold_guard_cells) && c.threshold_guard_cells >= 0.0 &&
        c.max_expansions >= 1 && c.required_stable_expansions >= 1 &&
        c.required_stable_expansions <= c.max_expansions))
    throw std::invalid_argument("Boltzmann Emax: invalid convergence controls");
  for (double threshold : c.required_thresholds_eV)
    if (!(std::isfinite(threshold) && threshold >= 0.0))
      throw std::invalid_argument("Boltzmann Emax: invalid required threshold");
}

// Callback: EnergyCeilingSample solve_at_emax(double emax).
// Requiring multiple consecutive independent solves prevents a single
// coincidental match from being mistaken for convergence.
template <typename SolveAtEnergy>
EnergyCeilingSelection selectEnergyCeiling(double initial,
                                          const EnergyCeilingControls & controls,
                                          SolveAtEnergy && solve_at_energy)
{
  validateEnergyCeilingControls(initial, controls);
  EnergyCeilingSelection selected;
  double emax = initial;
  EnergyCeilingSample previous;
  bool has_previous = false;
  std::size_t stable_count = 0;
  for (std::size_t iteration = 0; iteration <= controls.max_expansions; ++iteration)
  {
    EnergyCeilingSample current = solve_at_energy(emax);
    EnergyCeilingIteration step = inspectEnergyCeilingSample(current, emax, controls);
    if (has_previous)
    {
      const double previous_mean = previous.distribution.mean_energy_eV;
      step.mean_relative_change = std::abs(step.mean_energy_eV - previous_mean) /
          std::max(step.mean_energy_eV, previous_mean);
      if (current.rates_m3_per_s.size() != previous.rates_m3_per_s.size())
        throw std::invalid_argument("Boltzmann Emax: monitored rate inventory changed");
      step.maximum_rate_relative_change = 0.0;
      for (std::size_t i = 0; i < current.rates_m3_per_s.size(); ++i)
      {
        const double a = current.rates_m3_per_s[i];
        const double b = previous.rates_m3_per_s[i];
        const double scale = std::max(std::abs(a), std::abs(b));
        const double difference = scale == 0.0 ? 0.0 : std::abs(a - b) / scale;
        step.maximum_rate_relative_change =
            std::max(step.maximum_rate_relative_change, difference);
      }
      step.stable =
          step.tail_number_fraction <= controls.tail_mass_limit &&
          step.tail_energy_fraction <= controls.tail_energy_limit &&
          step.mean_relative_change <= controls.moment_relative_limit &&
          step.maximum_rate_relative_change <= controls.rate_relative_limit &&
          step.threshold_resolved;
      stable_count = step.stable ? stable_count + 1 : 0;
    }
    selected.history.push_back(step);
    selected.distribution = current.distribution;
    if (stable_count >= controls.required_stable_expansions)
    {
      selected.converged = true;
      selected.status = step.rates_monitored ?
          "CONVERGED_MONITORED_RATES_SCIENCE_HOLD" :
          "CONVERGED_MOMENTS_ONLY_RATES_NOT_MONITORED_SCIENCE_HOLD";
      return selected;
    }
    if (iteration == controls.max_expansions)
    {
      selected.status = "HOLD_MAX_EXPANSIONS";
      return selected;
    }
    const double next = std::min(controls.maximum_energy_eV,
                                 emax * controls.expansion_factor);
    if (!(next > emax))
    {
      selected.status = "HOLD_MAX_ENERGY_LIMIT";
      return selected;
    }
    previous = std::move(current);
    has_previous = true;
    emax = next;
  }
  return selected;
}

// First production-independent integration: actually re-solve the C++ elastic
// model at every trial ceiling while preserving the nominal FV cell width.
// Custom meshes and coupled inelastic physics need a separate re-projection
// callback; never silently rescale or reuse their collision operators.
inline EnergyCeilingSelection solveElasticWithAutomaticCeiling(
    const ElasticInput & initial, const EnergyCeilingControls & controls)
{
  validateEnergyCeilingControls(initial.max_energy_eV, controls);
  if (!initial.energy_cell_edges_eV.empty())
    throw std::invalid_argument("Boltzmann Emax: automatic elastic path requires uniform initial mesh");
  for (const auto & target : initial.targets)
    if (target.energy_eV.empty() || target.energy_eV.back() < controls.maximum_energy_eV)
      throw std::invalid_argument("Boltzmann Emax: cross-section domain does not cover maximum ceiling");
  return selectEnergyCeiling(initial.max_energy_eV, controls, [&](double emax) {
    ElasticInput next = initial;
    next.max_energy_eV = emax;
    const double requested = std::ceil(
        static_cast<double>(initial.cells) * emax / initial.max_energy_eV);
    if (!(std::isfinite(requested) && requested >= 2.0 && requested <= 16384.0))
      throw std::invalid_argument("Boltzmann Emax: required FV cell count exceeds 16384");
    next.cells = static_cast<std::size_t>(requested);
    return EnergyCeilingSample{solveElasticSteadyState(next), {}};
  });
}
} // namespace PhysicsBoltzmann
