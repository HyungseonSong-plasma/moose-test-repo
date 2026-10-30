#pragma once

#include "PhysicsBoltzmannElasticSolver.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace PhysicsBoltzmann
{
// Shared FV geometry; default empty optional edges preserves original uniform
// results without rewriting the collision input's physical Emax.
inline std::vector<double> energyMeshEdges(const ElasticInput & input)
{
  if (!(std::isfinite(input.max_energy_eV) && input.max_energy_eV > 0.0) ||
      input.cells < 2)
    throw std::invalid_argument("Boltzmann mesh: invalid Emax or cell count");
  if (input.energy_cell_edges_eV.empty())
  {
    std::vector<double> edges(input.cells + 1);
    for (std::size_t i = 0; i <= input.cells; ++i)
      edges[i] = input.max_energy_eV *
          static_cast<double>(i) / static_cast<double>(input.cells);
    return edges;
  }
  const auto & edges = input.energy_cell_edges_eV;
  if (edges.size() != input.cells + 1 || edges.front() != 0.0 ||
      edges.back() != input.max_energy_eV)
    throw std::invalid_argument(
        "Boltzmann mesh: nonuniform edges must start at zero and end at Emax");
  for (std::size_t i = 1; i < edges.size(); ++i)
    if (!(std::isfinite(edges[i]) && edges[i] > edges[i - 1]))
      throw std::invalid_argument("Boltzmann mesh: edges must increase strictly");
  return edges;
}

inline std::vector<double> energyMeshCenters(const std::vector<double> & edges)
{
  std::vector<double> centers(edges.size() - 1);
  for (std::size_t i = 0; i < centers.size(); ++i)
    centers[i] = 0.5 * (edges[i] + edges[i + 1]);
  return centers;
}

// Point e in [0,Emax] -> cell, including the uppermost endpoint.
inline std::size_t energyMeshCell(const std::vector<double> & edges, double e)
{
  if (!(std::isfinite(e) && e >= edges.front() && e <= edges.back()))
    throw std::invalid_argument("Boltzmann mesh: energy outside mesh");
  return std::min(
      static_cast<std::size_t>(std::upper_bound(edges.begin(), edges.end(), e) -
                               edges.begin() - 1), edges.size() - 2);
}

// Smooth power-law mapping supports low-energy refinement without unverified
// BOLSIG+ automatic-grid claims. power=1 is uniform, power>1 clusters near 0.
inline std::vector<double> powerLawEnergyMesh(
    std::size_t cells, double emax_eV, double exponent)
{
  if (cells < 2 || cells > 16384 ||
      !(std::isfinite(emax_eV) && emax_eV > 0.0) ||
      !(std::isfinite(exponent) && exponent >= 1.0 && exponent <= 4.0))
    throw std::invalid_argument("Boltzmann mesh: invalid power-law grid request");
  std::vector<double> edges(cells + 1);
  for (std::size_t i = 0; i <= cells; ++i)
  {
    const double x = static_cast<double>(i) / static_cast<double>(cells);
    edges[i] = emax_eV * std::pow(x, exponent);
  }
  edges.front() = 0.0;
  edges.back() = emax_eV;
  for (std::size_t i = 1; i < edges.size(); ++i)
    if (!(edges[i] > edges[i-1]))
      throw std::invalid_argument("Boltzmann mesh: degenerate power-law grid");
  return edges;
}
} // namespace PhysicsBoltzmann
