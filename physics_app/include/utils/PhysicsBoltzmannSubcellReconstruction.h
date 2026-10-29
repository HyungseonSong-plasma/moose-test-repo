#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <vector>

namespace PhysicsBoltzmann
{
// A nonnegative affine f0(E) within each FV cell, normalized against the
// physical sqrt(E) electron-number measure. Slopes are frozen while the
// linear growth operator is assembled; a nonlinear Picard loop must update
// them before a reconstructed eigenstate can be called self-consistent.
struct SubcellReconstruction
{
  std::vector<double> mass_centroids_eV;
  std::vector<double> relative_slopes_per_eV;
  std::vector<double> cell_number_masses;
};

inline SubcellReconstruction reconstructConservativeSubcells(
    const std::vector<double> & edges,
    const std::vector<double> & cell_eepf)
{
  const auto n = cell_eepf.size();
  if (n < 2 || edges.size() != n + 1 || edges.front() != 0.0)
    throw std::invalid_argument("Boltzmann P0-3: invalid reconstruction geometry");
  SubcellReconstruction out;
  out.mass_centroids_eV.resize(n);
  out.relative_slopes_per_eV.resize(n);
  out.cell_number_masses.resize(n);
  std::vector<double> centers(n);
  double normalization = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    const double a = edges[i], b = edges[i + 1];
    if (!(std::isfinite(a) && std::isfinite(b) && b > a &&
          std::isfinite(cell_eepf[i]) && cell_eepf[i] >= 0.0))
      throw std::invalid_argument("Boltzmann P0-3: invalid energy edges or EEPF");
    const double mass = (2.0 / 3.0) * (std::pow(b, 1.5) - std::pow(a, 1.5));
    const double moment = (2.0 / 5.0) * (std::pow(b, 2.5) - std::pow(a, 2.5));
    if (!(std::isfinite(mass) && mass > 0.0 && std::isfinite(moment)))
      throw std::invalid_argument("Boltzmann P0-3: degenerate number mass");
    out.cell_number_masses[i] = mass;
    out.mass_centroids_eV[i] = moment / mass;
    centers[i] = 0.5 * (a + b);
    normalization += cell_eepf[i] * mass;
  }
  if (!(std::isfinite(normalization) && std::abs(normalization - 1.0) < 1e-8))
    throw std::invalid_argument("Boltzmann P0-3: reference EEPF must be normalized");

  for (std::size_t i = 0; i < n; ++i)
  {
    if (cell_eepf[i] == 0.0)
      continue; // no negative or spurious tail from a zero donor cell
    const auto secant = [&](std::size_t a, std::size_t b)
    {
      return (cell_eepf[b] - cell_eepf[a]) / (centers[b] - centers[a]);
    };
    double absolute_slope = 0.0;
    if (i == 0)
      absolute_slope = secant(0, 1);
    else if (i + 1 == n)
      absolute_slope = secant(n - 2, n - 1);
    else
    {
      const double left = secant(i - 1, i);
      const double right = secant(i, i + 1);
      if ((left > 0.0 && right > 0.0) ||
          (left < 0.0 && right < 0.0))
        absolute_slope = std::copysign(std::min(std::abs(left), std::abs(right)), left);
    }
    double slope = absolute_slope / cell_eepf[i];
    const double mu = out.mass_centroids_eV[i];
    // Since f(E)=f_i[1+s(E-mu)], these bounds guarantee f(E)>=0
    // everywhere, including a one-sided high-energy tail extrapolation.
    slope = std::max(-1.0 / (edges[i + 1] - mu),
                     std::min(1.0 / (mu - edges[i]), slope));
    if (!std::isfinite(slope))
      throw std::invalid_argument("Boltzmann P0-3: non-finite limited slope");
    out.relative_slopes_per_eV[i] = slope;
  }
  return out;
}

// Exact integral of E*sigma(E)*[1+s(E-mu)] dE for a piecewise-linear
// cross section. Integrating in local coordinates prevents cancellation
// between nearly equal large powers at a threshold near Emax.
inline double integrateSubcellEnergyCrossSection(
    const std::vector<double> & energy,
    const std::vector<double> & sigma,
    double lo, double hi, double mu, double relative_slope)
{
  if (energy.size() < 2 || sigma.size() != energy.size() ||
      !std::isfinite(lo) || !std::isfinite(hi) || lo < 0.0 || hi < lo ||
      !std::isfinite(mu) || !std::isfinite(relative_slope) ||
      energy.front() > lo || energy.back() < hi)
    throw std::invalid_argument("Boltzmann P0-3: invalid subcell integral domain");
  if (hi == lo)
    return 0.0;
  double result = 0.0;
  for (std::size_t i = 0; i < energy.size(); ++i)
    if (!std::isfinite(energy[i]) || !std::isfinite(sigma[i]) ||
        sigma[i] < 0.0 || (i && energy[i] <= energy[i - 1]))
      throw std::invalid_argument("Boltzmann P0-3: invalid cross-section table");
  if (1.0 + relative_slope * (lo - mu) < -1e-12 ||
      1.0 + relative_slope * (hi - mu) < -1e-12)
    throw std::invalid_argument("Boltzmann P0-3: reconstruction became negative");
  while (lo < hi)
  {
    const auto upper = std::upper_bound(energy.begin(), energy.end(), lo);
    std::size_t j = upper == energy.begin() ? 0 :
        static_cast<std::size_t>(upper - energy.begin() - 1);
    j = std::min(j, energy.size() - 2);
    const double right = std::min(hi, energy[j + 1]);
    if (!(right > lo))
      throw std::runtime_error("Boltzmann P0-3: subcell integral did not advance");
    const double ds = (sigma[j + 1] - sigma[j]) / (energy[j + 1] - energy[j]);
    const double s0 = sigma[j] + ds * (lo - energy[j]);
    const double a = 1.0 + relative_slope * (lo - mu);
    const double b = relative_slope;
    const double p0 = lo * s0 * a;
    const double p1 = lo * s0 * b + (lo * ds + s0) * a;
    const double p2 = (lo * ds + s0) * b + ds * a;
    const double p3 = ds * b;
    const double h = right - lo;
    result += h * (p0 + h * (p1 / 2.0 + h * (p2 / 3.0 + h * p3 / 4.0)));
    lo = right;
  }
  if (!std::isfinite(result) || result < -1e-24)
    throw std::runtime_error("Boltzmann P0-3: invalid reconstructed rate integral");
  return std::max(0.0, result);
}
} // namespace PhysicsBoltzmann
