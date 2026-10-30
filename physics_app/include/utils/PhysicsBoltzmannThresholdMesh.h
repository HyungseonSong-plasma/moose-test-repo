#pragma once

#include "PhysicsBoltzmannElasticSolver.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

namespace PhysicsBoltzmann
{
// P0-2 DEVELOPMENT ONLY. A deterministic threshold-aware conservative FV
// energy grid. This does NOT reconstruct within-cell f0, solve an adaptive
// error estimator, or reproduce BOLSIG+'s automatic grid.
struct ThresholdMeshControls
{
  double low_energy_power = 2.0;
  std::size_t threshold_side_cells = 4;
  double threshold_refinement_factor = 4.0;
  double tail_window_fraction = 0.12;
  std::size_t tail_cells = 12;
  std::size_t maximum_cells = 256; // M6b dense reference budget
};

struct ThresholdMeshResult
{
  std::vector<double> edges_eV;
  std::size_t threshold_faces = 0;
  double minimum_width_eV = 0.0;
  double maximum_tail_width_eV = 0.0;
};

inline ThresholdMeshResult buildThresholdAwareMesh(
    double emax, std::size_t base_cells,
    const std::vector<double> & active_thresholds,
    const ThresholdMeshControls & c = {})
{
  if (!(std::isfinite(emax) && emax > 0.0 &&
        std::isfinite(c.low_energy_power) && c.low_energy_power >= 1.0 &&
        std::isfinite(c.threshold_refinement_factor) &&
        c.threshold_refinement_factor >= 1.0 &&
        std::isfinite(c.tail_window_fraction) &&
        c.tail_window_fraction > 0.0 && c.tail_window_fraction < 1.0 &&
        base_cells >= 2 && c.threshold_side_cells >= 1 &&
        c.tail_cells >= 2 && c.maximum_cells >= base_cells))
    throw std::invalid_argument("Boltzmann P0-2: invalid threshold mesh controls");

  // Tag 4 = immutable endpoints, 3 = exact threshold, 2 = local
  // threshold refinement, 1 = tail refinement, 0 = base grid.
  // In near-coincident groups retain the highest-priority face.
  std::vector<std::pair<double, int>> points;
  points.reserve(base_cells + 2 * active_thresholds.size() *
      (c.threshold_side_cells + 1) + c.tail_cells + 4);
  const auto add = [&](double e, int priority) {
    if (std::isfinite(e) && e >= 0.0 && e <= emax)
      points.emplace_back(e, priority);
  };
  std::vector<double> base(base_cells + 1);
  for (std::size_t i = 0; i <= base_cells; ++i)
  {
    const double x = static_cast<double>(i) / static_cast<double>(base_cells);
    base[i] = emax * std::pow(x, c.low_energy_power);
    add(base[i], (i == 0 || i == base_cells) ? 4 : 0);
  }

  const double min_gap = 64.0 * std::numeric_limits<double>::epsilon() * emax;
  for (double t : active_thresholds)
  {
    if (!(std::isfinite(t) && t > min_gap && t < emax - min_gap))
      throw std::invalid_argument(
          "Boltzmann P0-2: active threshold outside resolvable (0,Emax)");
    const auto upper = std::upper_bound(base.begin(), base.end(), t);
    const std::size_t right = static_cast<std::size_t>(upper - base.begin());
    if (right == 0 || right >= base.size())
      throw std::invalid_argument("Boltzmann P0-2: invalid threshold bracket");
    const double base_width = base[right] - base[right - 1];
    const double local_step = base_width / c.threshold_refinement_factor;
    const double below = std::min(local_step,
        t / static_cast<double>(c.threshold_side_cells));
    const double above = std::min(local_step,
        (emax - t) / static_cast<double>(c.threshold_side_cells));
    if (!(below > min_gap && above > min_gap))
      throw std::invalid_argument("Boltzmann P0-2: threshold cannot be resolved");
    add(t, 3);
    for (std::size_t j = 1; j <= c.threshold_side_cells; ++j)
    {
      add(t - static_cast<double>(j) * below, 2);
      add(t + static_cast<double>(j) * above, 2);
    }
  }

  const double tail_start = emax * (1.0 - c.tail_window_fraction);
  for (std::size_t j = 0; j <= c.tail_cells; ++j)
    add(tail_start + (emax - tail_start) *
        static_cast<double>(j) / static_cast<double>(c.tail_cells), 1);

  std::sort(points.begin(), points.end(),
      [](const auto & a, const auto & b) {
        return a.first < b.first ||
            (a.first == b.first && a.second > b.second);
      });
  ThresholdMeshResult result;
  std::vector<std::pair<double, int>> unique;
  for (const auto & p : points)
  {
    if (unique.empty() || p.first - unique.back().first > min_gap)
      unique.push_back(p);
    else if (p.second > unique.back().second)
      unique.back() = p;
  }
  if (unique.size() < 3 || unique.front().first != 0.0 ||
      unique.back().first != emax)
    throw std::runtime_error("Boltzmann P0-2: invalid mesh endpoints");

  if (unique.size() - 1 > c.maximum_cells)
    throw std::runtime_error("Boltzmann P0-2: HOLD_DENSE_REFERENCE_CELL_LIMIT");
  result.edges_eV.reserve(unique.size());
  result.minimum_width_eV = emax;
  for (std::size_t i = 0; i < unique.size(); ++i)
  {
    result.edges_eV.push_back(unique[i].first);
    if (i)
    {
      const double width = unique[i].first - unique[i - 1].first;
      if (!(std::isfinite(width) && width > min_gap))
        throw std::runtime_error("Boltzmann P0-2: non-increasing FV faces");
      result.minimum_width_eV = std::min(result.minimum_width_eV, width);
      if (unique[i - 1].first >= tail_start)
        result.maximum_tail_width_eV =
            std::max(result.maximum_tail_width_eV, width);
    }
  }
  for (double t : active_thresholds)
  {
    const auto it = std::lower_bound(result.edges_eV.begin(),
                                     result.edges_eV.end(), t);
    if (it == result.edges_eV.end() || *it != t)
      throw std::runtime_error("Boltzmann P0-2: active threshold face missing");
    ++result.threshold_faces;
  }
  if (!(result.maximum_tail_width_eV <=
        (emax - tail_start) / static_cast<double>(c.tail_cells) *
            (1.0 + 1e-10)))
    throw std::runtime_error("Boltzmann P0-2: high-energy tail underresolved");
  return result;
}

inline ElasticInput withThresholdAwareMesh(
    const ElasticInput & input, const std::vector<double> & active_thresholds,
    const ThresholdMeshControls & controls = {})
{
  if (!input.energy_cell_edges_eV.empty())
    throw std::invalid_argument(
        "Boltzmann P0-2: refuse to overwrite an existing custom mesh");
  ElasticInput refined = input;
  const auto mesh = buildThresholdAwareMesh(
      input.max_energy_eV, input.cells, active_thresholds, controls);
  refined.energy_cell_edges_eV = mesh.edges_eV;
  refined.cells = mesh.edges_eV.size() - 1;
  return refined;
}
} // namespace PhysicsBoltzmann
