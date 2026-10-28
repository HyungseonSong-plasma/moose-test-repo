#include "PhysicsBoltzmannTemporalGrowth.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

namespace PhysicsBoltzmann
{
namespace
{
constexpr double qe = 1.602176634e-19;
constexpr double me = 9.1093837139e-31;
constexpr double kB = 1.380649e-23;
const double gamma = std::sqrt(2.0 * qe / me);

double interpolate(const ElasticTarget & target, double e)
{
  const auto upper = std::upper_bound(target.energy_eV.begin(), target.energy_eV.end(), e);
  if (upper == target.energy_eV.begin())
    return target.momentum_transfer_m2.front();
  if (upper == target.energy_eV.end())
    return target.momentum_transfer_m2.back();
  const auto k = static_cast<std::size_t>(upper - target.energy_eV.begin());
  const double t = (e - target.energy_eV[k - 1]) /
                   (target.energy_eV[k] - target.energy_eV[k - 1]);
  return (1.0 - t) * target.momentum_transfer_m2[k - 1] +
         t * target.momentum_transfer_m2[k];
}

double bernoulli(double x)
{
  if (std::abs(x) < 1e-4)
    return 1.0 - x / 2.0 + x * x / 12.0 - x * x * x * x / 720.0;
  if (x > 50.0)
    return x * std::exp(-x) / (1.0 - std::exp(-x));
  if (x < -50.0)
    return -x / (1.0 - std::exp(x));
  return x / std::expm1(x);
}

struct DenseLU
{
  std::vector<std::vector<double>> a;
  std::vector<std::size_t> swaps;

  explicit DenseLU(std::vector<std::vector<double>> matrix) : a(std::move(matrix))
  {
    const auto n = a.size();
    swaps.resize(n);
    for (std::size_t k = 0; k < n; ++k)
    {
      std::size_t p = k;
      for (std::size_t i = k + 1; i < n; ++i)
        if (std::abs(a[i][k]) > std::abs(a[p][k]))
          p = i;
      if (!(std::abs(a[p][k]) > 1e-22) || !std::isfinite(a[p][k]))
        throw std::runtime_error("Boltzmann M6b: singular shifted temporal-growth system");
      swaps[k] = p;
      std::swap(a[p], a[k]);
      for (std::size_t i = k + 1; i < n; ++i)
      {
        a[i][k] /= a[k][k];
        for (std::size_t j = k + 1; j < n; ++j)
          a[i][j] -= a[i][k] * a[k][j];
      }
    }
  }

  std::vector<double> solve(std::vector<double> b) const
  {
    const auto n = a.size();
    for (std::size_t i = 0; i < n; ++i)
    {
      std::swap(b[i], b[swaps[i]]);
      for (std::size_t j = i + 1; j < n; ++j)
        b[j] -= a[j][i] * b[i];
    }
    for (std::size_t i = n; i-- > 0;)
    {
      for (std::size_t j = i + 1; j < n; ++j)
        b[i] -= a[i][j] * b[j];
      b[i] /= a[i][i];
      if (!std::isfinite(b[i]))
        throw std::runtime_error("Boltzmann M6b: non-finite inverse iteration");
    }
    return b;
  }
};
} // namespace

TemporalGrowthResult solveElasticTemporalGrowth(
    const ElasticInput & input,
    const std::vector<IonizationChannel> & ionizations,
    const std::vector<AttachmentChannel> & attachments)
{
  if (input.cells > 128 || input.cells < 2)
    throw std::invalid_argument("Boltzmann M6b: dense eigen reference limited to [2,128] cells");
  if (!std::isfinite(input.reduced_field_Td) || input.reduced_field_Td < 0.0 ||
      !std::isfinite(input.gas_temperature_K) || input.gas_temperature_K <= 0.0)
    throw std::invalid_argument("Boltzmann M6b: invalid E/N or gas temperature");

  // Use the validated M6 operator as the one source of number-changing
  // transfer coefficients; do not reimplement its equal-sharing rule here.
  const auto growth_op = assembleGrowthCollisions(input, ionizations, attachments);
  const std::size_t n = input.cells;
  const double h = input.max_energy_eV / n;
  std::vector<std::vector<double>> a(n, std::vector<double>(n, 0.0));

  for (const auto & entry : growth_op.entries)
    a[entry.destination][entry.donor] -= entry.coefficient_m3_per_s;

  // Elastic-only two-term DC Scharfetter-Gummel transport. The inverse
  // iteration remains separately bounded until excitation/superelastic
  // scattering and sparse growth eigensolvers are incorporated.
  double fraction_sum = 0.0;
  for (const auto & target : input.targets)
  {
    if (target.energy_eV.size() < 2 ||
        target.momentum_transfer_m2.size() != target.energy_eV.size() ||
        target.energy_eV.front() > 0.0 ||
        target.energy_eV.back() < input.max_energy_eV ||
        !(target.mole_fraction > 0.0 && target.electron_mass_ratio > 0.0))
      throw std::invalid_argument("Boltzmann M6b: elastic gas collision table incomplete");
    fraction_sum += target.mole_fraction;
    for (std::size_t i = 0; i < target.energy_eV.size(); ++i)
      if (!(std::isfinite(target.energy_eV[i]) &&
            std::isfinite(target.momentum_transfer_m2[i]) &&
            target.momentum_transfer_m2[i] >= 0.0) ||
          (i && target.energy_eV[i] <= target.energy_eV[i - 1]))
        throw std::invalid_argument("Boltzmann M6b: invalid elastic collision coordinates");
  }
  if (std::abs(fraction_sum - 1.0) > 1e-12)
    throw std::invalid_argument("Boltzmann M6b: gas fractions do not sum to one");

  const double EN = input.reduced_field_Td * 1e-21;
  const double theta = kB * input.gas_temperature_K / qe;
  for (std::size_t i = 1; i < n; ++i)
  {
    const double e = i * h;
    double sigma_m = 0.0, sigma_e = 0.0;
    for (const auto & t : input.targets)
    {
      const double xs = t.mole_fraction * interpolate(t, e);
      sigma_m += xs;
      sigma_e += 2.0 * t.electron_mass_ratio * xs;
    }
    if (!(sigma_m > 0.0 && sigma_e > 0.0))
      throw std::invalid_argument("Boltzmann M6b: vanishing elastic collision frequency");
    const double W = -gamma * e * e * sigma_e;
    const double D = gamma * ((EN * EN / 3.0) * e / sigma_m +
                              theta * e * e * sigma_e);
    if (!(D > 0.0 && std::isfinite(D)))
      throw std::runtime_error("Boltzmann M6b: elastic SG coefficient invalid");
    const double P = W * h / D;
    const double left = D / h * bernoulli(-P);
    const double right = D / h * bernoulli(P);
    a[i - 1][i - 1] += left;
    a[i - 1][i] -= right;
    a[i][i - 1] -= left;
    a[i][i] += right;
  }

  // For each donor, ionization/attachment electron production is
  // bounded by ionization_event_columns / M_i. A shift larger than this
  // bound makes (A + shift*M) a nonsingular M-matrix, assuming positive
  // finite-mass elastic transport coefficients.
  double upper_bound = 0.0;
  for (std::size_t i = 0; i < n; ++i)
    upper_bound = std::max(upper_bound,
        growth_op.ionization_event_columns[i] / growth_op.electron_number_mass[i]);
  const double shift = std::max(1e-20, upper_bound * 1.05);
  auto shifted = a;
  for (std::size_t i = 0; i < n; ++i)
    shifted[i][i] += shift * growth_op.electron_number_mass[i];
  const DenseLU lu(std::move(shifted));

  // Use the M1 validated elastic EEPF as an initial positive iterate.
  const auto seed = solveElasticSteadyState(input);
  std::vector<double> f = seed.eepf_eV_minus_3_halves;
  double growth_lambda = 0.0;
  std::size_t iterations = 0;
  bool converged = false;
  constexpr std::size_t max_iterations = 8000;
  for (std::size_t iteration = 0; iteration < max_iterations; ++iteration)
  {
    std::vector<double> rhs(n);
    for (std::size_t i = 0; i < n; ++i)
      rhs[i] = f[i] * growth_op.electron_number_mass[i];
    auto next = lu.solve(std::move(rhs));
    const double max_next = *std::max_element(next.begin(), next.end());
    if (!(max_next > 0.0))
      throw std::runtime_error("Boltzmann M6b: nonpositive dominant growth eigenvector");
    for (auto & value : next)
    {
      if (!std::isfinite(value) || value < -max_next * 1e-11)
        throw std::runtime_error("Boltzmann M6b: lost Perron eigenvector positivity");
      value = std::max(0.0, value);
    }
    double normalizer = 0.0;
    for (std::size_t i = 0; i < n; ++i)
      normalizer += next[i] * growth_op.electron_number_mass[i];
    if (!(normalizer > 0.0 && std::isfinite(normalizer)))
      throw std::runtime_error("Boltzmann M6b: growth normalization failed");
    double delta = 0.0;
    for (std::size_t i = 0; i < n; ++i)
    {
      next[i] /= normalizer;
      delta += growth_op.electron_number_mass[i] * std::abs(next[i] - f[i]);
    }
    f = std::move(next);
    iterations = iteration + 1;
    if (delta < 5e-11)
    {
      converged = true;
      break;
    }
  }
  if (!converged)
    throw std::runtime_error("Boltzmann M6b: shifted temporal-growth eigenvector not converged");

  TemporalGrowthResult out;
  out.distribution.energy_eV.resize(n);
  out.distribution.eepf_eV_minus_3_halves = f;
  out.distribution.normalization = 1.0;
  out.distribution.maximum_normalized_flux_residual =
      std::numeric_limits<double>::quiet_NaN();
  double energy = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    const double lo = i * h, hi = (i + 1) * h;
    out.distribution.energy_eV[i] = (i + 0.5) * h;
    energy += f[i] * (2.0 / 5.0) * (std::pow(hi, 2.5) - std::pow(lo, 2.5));
  }
  out.distribution.mean_energy_eV = energy;
  out.growth = evaluateGrowthOnFrozenEepf(input, out.distribution,
                                          ionizations, attachments);
  growth_lambda = out.growth.reduced_temporal_growth_m3_per_s;
  out.reduced_growth_eigenvalue_m3_per_s = growth_lambda;
  out.inverse_iterations = iterations;

  double numerator = 0.0, denominator = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    double ri = growth_lambda * growth_op.electron_number_mass[i] * f[i];
    double magnitude = std::abs(ri);
    for (std::size_t j = 0; j < n; ++j)
    {
      const double term = a[i][j] * f[j];
      ri += term;
      magnitude += std::abs(term);
    }
    numerator += std::abs(ri);
    denominator += magnitude;
  }
  out.maximum_normalized_eigen_residual =
      denominator > 0.0 ? numerator / denominator : 0.0;
  if (!(out.maximum_normalized_eigen_residual < 1e-8))
    throw std::runtime_error("Boltzmann M6b: true generalized eigen residual exceeds 1e-8");
  return out;
}
} // namespace PhysicsBoltzmann
