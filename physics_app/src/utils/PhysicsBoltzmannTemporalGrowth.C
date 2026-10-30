#include "PhysicsBoltzmannTemporalGrowth.h"
#include "PhysicsBoltzmannEnergyMesh.h"
#include "PhysicsBoltzmannSubcellReconstruction.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>
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

double interpolate(const std::vector<double> & energy,
                   const std::vector<double> & sigma, double e)
{
  const auto upper = std::upper_bound(energy.begin(), energy.end(), e);
  if (upper == energy.begin())
    return sigma.front();
  if (upper == energy.end())
    return sigma.back();
  const auto k = static_cast<std::size_t>(upper - energy.begin());
  const double t = (e - energy[k - 1]) / (energy[k] - energy[k - 1]);
  return (1.0 - t) * sigma[k - 1] + t * sigma[k];
}

double interpolate(const ElasticTarget & target, double e)
{
  return interpolate(target.energy_eV, target.momentum_transfer_m2, e);
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
    const std::vector<AttachmentChannel> & attachments,
    const std::vector<ExcitationChannel> & excitations,
    const std::vector<double> & reference_eepf)
{
  // The 07/2024 BOLSIG+ Example 4 reference uses 200 automatic-grid
  // cells. Raise the *development-only* dense eigen reference bound to
  // 256, covered by 200-cell eigenpair/rate and weak-growth controls.
  // A sparse scalable production eigensolver remains a separate gate.
  if (input.cells > 256 || input.cells < 2)
    throw std::invalid_argument("Boltzmann M6b: dense eigen reference limited to [2,256] cells");
  if (!std::isfinite(input.reduced_field_Td) || input.reduced_field_Td < 0.0 ||
      !std::isfinite(input.reduced_angular_frequency_m3_per_s) ||
      input.reduced_angular_frequency_m3_per_s < 0.0 ||
      !std::isfinite(input.gas_temperature_K) || input.gas_temperature_K <= 0.0)
    throw std::invalid_argument("Boltzmann M6b: invalid E/N or gas temperature");

  // Use the validated M6 operator as the one source of number-changing
  // transfer coefficients; do not reimplement its equal-sharing rule here.
  const auto growth_op = assembleGrowthCollisions(
      input, ionizations, attachments, reference_eepf);
  const std::size_t n = input.cells;
  const auto edges = energyMeshEdges(input);
  const auto centers = energyMeshCenters(edges);
  std::vector<std::vector<double>> a(n, std::vector<double>(n, 0.0));

  for (const auto & entry : growth_op.entries)
    a[entry.destination][entry.donor] -= entry.coefficient_m3_per_s;

  // Both steady M5 and growing M6b2 must use exactly the same
  // two-term field-heating and shifted excitation/superelastic collision
  // discretization. The M5 assembly is conserved and shares this operator.
  // This avoids independently rederiving nonlocal inelastic gain/loss.
  if (!excitations.empty())
  {
    const auto excited = assembleExcitationConservativeOperator(input, excitations);
    if (!(excited.maximum_collision_number_balance_error < 1e-9))
      throw std::runtime_error("Boltzmann M6b2: excitation operator conservation failed");
    for (std::size_t i = 0; i < n; ++i)
      for (const auto & [j, value] : excited.rows[i])
        a[i][j] += value;
  }

  // Elastic-only SG branch preserves independently validated M6b1
  // assembly and provides a known-good zero-excitation control.
  double fraction_sum = 0.0;
  for (const auto & target : input.targets)
  {
    if (target.energy_eV.size() < 2 ||
        target.momentum_transfer_m2.size() != target.energy_eV.size() ||
        (!target.field_momentum_transfer_m2.empty() &&
         target.field_momentum_transfer_m2.size() != target.energy_eV.size()) ||
        target.energy_eV.front() > 0.0 ||
        target.energy_eV.back() < input.max_energy_eV ||
        !(target.mole_fraction > 0.0 && target.electron_mass_ratio > 0.0))
      throw std::invalid_argument("Boltzmann M6b: elastic gas collision table incomplete");
    fraction_sum += target.mole_fraction;
    for (std::size_t i = 0; i < target.energy_eV.size(); ++i)
      if (!(std::isfinite(target.energy_eV[i]) &&
            std::isfinite(target.momentum_transfer_m2[i]) &&
            target.momentum_transfer_m2[i] >= 0.0 &&
            (target.field_momentum_transfer_m2.empty() ||
             (std::isfinite(target.field_momentum_transfer_m2[i]) &&
              target.field_momentum_transfer_m2[i] >= 0.0))) ||
          (i && target.energy_eV[i] <= target.energy_eV[i - 1]))
        throw std::invalid_argument("Boltzmann M6b: invalid elastic collision coordinates");
  }
  if (std::abs(fraction_sum - 1.0) > 1e-12)
    throw std::invalid_argument("Boltzmann M6b: gas fractions do not sum to one");

  const double EN = input.reduced_field_Td * 1e-21;
  const double theta = kB * input.gas_temperature_K / qe;
  if (excitations.empty())
  for (std::size_t i = 1; i < n; ++i)
  {
    const double e = edges[i];
    const double delta = centers[i]-centers[i-1];
    double sigma_m = 0.0, sigma_e = 0.0;
    for (const auto & t : input.targets)
    {
      const double xs = t.mole_fraction * interpolate(t, e);
      if (t.field_momentum_transfer_m2.empty())
        sigma_m += xs;
      else
      {
        sigma_m += t.mole_fraction *
                   interpolate(t.energy_eV, t.field_momentum_transfer_m2, e);
      }
      sigma_e += 2.0 * t.electron_mass_ratio * xs;
    }
    if (!(sigma_m > 0.0 && sigma_e > 0.0))
      throw std::invalid_argument("Boltzmann M6b: vanishing elastic collision frequency");
    const double W = -gamma * e * e * sigma_e;
    const double q = input.reduced_angular_frequency_m3_per_s;
    const double Q = gamma * std::sqrt(e) * sigma_m;
    const double suppression = q == 0.0 ? 1.0 :
        1.0 / (1.0 + (q/Q)*(q/Q));
    const double D = gamma * ((EN * EN / 3.0) * e / sigma_m * suppression +
                              theta * e * e * sigma_e);
    if (!(D > 0.0 && std::isfinite(D)))
      throw std::runtime_error("Boltzmann M6b: elastic SG coefficient invalid");
    const double P = W * delta / D;
    const double left = D / delta * bernoulli(-P);
    const double right = D / delta * bernoulli(P);
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
  // Begin with a provably safe ionization-source upper bound, then
  // reduce the shift toward the current Rayleigh growth estimate. A fixed
  // overconservative shift makes pure-ionization inverse iteration orders of
  // magnitude slower than necessary. Each smaller shift is accepted ONLY
  // if the independently solved resolvent retains a positive iterate.
  double shift = std::max(1e-20, upper_bound * 1.05);
  std::vector<double> f;
  if (excitations.empty())
    f = solveElasticSteadyState(input).eepf_eV_minus_3_halves;
  else
    f = solveExcitationSteadyState(input, excitations).distribution.eepf_eV_minus_3_halves;
  double growth_lambda = 0.0;
  std::size_t iterations = 0;
  bool converged = false;
  constexpr std::size_t max_epochs = 12;
  constexpr std::size_t max_per_epoch = 200;
  const auto growthEstimate = [&](const std::vector<double> & state)
  {
    double value = 0.0;
    for (std::size_t i = 0; i < n; ++i)
      value += state[i] * (growth_op.ionization_event_columns[i] -
                           growth_op.attachment_event_columns[i]);
    return value;
  };
  const auto relativeEigenResidual = [&](const std::vector<double> & state)
  {
    const double lambda = growthEstimate(state);
    double numerator = 0.0, denominator = 0.0;
    for (std::size_t i = 0; i < n; ++i)
    {
      double ri = lambda * growth_op.electron_number_mass[i] * state[i];
      double magnitude = std::abs(ri);
      for (std::size_t j = 0; j < n; ++j)
      {
        const double term = a[i][j] * state[j];
        ri += term;
        magnitude += std::abs(term);
      }
      numerator += std::abs(ri);
      denominator += magnitude;
    }
    return denominator > 0.0 ? numerator / denominator : 0.0;
  };

  for (std::size_t epoch = 0; epoch < max_epochs; ++epoch)
  {
    const double estimated = growthEstimate(f);
    double candidate_shift = epoch == 0 ? shift :
        std::min(shift, std::max(1e-20, estimated +
                               std::max(1e-19, 0.02 * std::abs(estimated))));
    std::unique_ptr<DenseLU> factor;
    for (std::size_t attempt = 0; attempt < 20; ++attempt)
    {
      auto shifted = a;
      for (std::size_t i = 0; i < n; ++i)
        shifted[i][i] += candidate_shift * growth_op.electron_number_mass[i];
      try
      {
        auto trial = std::make_unique<DenseLU>(std::move(shifted));
        std::vector<double> rhs(n);
        for (std::size_t i = 0; i < n; ++i)
          rhs[i] = f[i] * growth_op.electron_number_mass[i];
        const auto probe = trial->solve(std::move(rhs));
        const auto extrema = std::minmax_element(probe.begin(), probe.end());
        if (*extrema.second > 0.0 &&
            *extrema.first >= -1e-11 * *extrema.second)
        {
          factor = std::move(trial);
          shift = candidate_shift;
          break;
        }
      }
      catch (const std::runtime_error &)
      {
        // Shift-invert breakdown is retryable; it never authorizes an
        // unvalidated eigenstate or suppressed final residual.
      }
      if (candidate_shift >= shift)
        break;
      candidate_shift = 0.5 * (candidate_shift + shift);
    }
    if (!factor)
      throw std::runtime_error("Boltzmann M6b: no positive shifted inverse resolvent");

    for (std::size_t iteration = 0; iteration < max_per_epoch; ++iteration)
    {
      std::vector<double> rhs(n);
      for (std::size_t i = 0; i < n; ++i)
        rhs[i] = f[i] * growth_op.electron_number_mass[i];
      auto next = factor->solve(std::move(rhs));
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
      ++iterations;
      if (delta < 5e-11)
        break;
    }
    if (relativeEigenResidual(f) < 1e-8)
    {
      converged = true;
      break;
    }
  }
  if (!converged)
    throw std::runtime_error("Boltzmann M6b: temporal-growth eigenpair failed true residual");

  TemporalGrowthResult out;
  out.distribution.energy_eV = centers;
  out.distribution.energy_cell_edges_eV = edges;
  out.distribution.eepf_eV_minus_3_halves = f;
  out.distribution.normalization = 1.0;
  out.distribution.maximum_normalized_flux_residual =
      std::numeric_limits<double>::quiet_NaN();
  // The optional Picard-frozen reconstruction changes the first energy
  // moment even though it preserves the sqrt(E)-weighted electron number.
  // Use the same subcell shape as Q; keep the legacy constant-cell moment
  // exactly when reconstruction is disabled.
  if (!reference_eepf.empty())
    out.distribution.mean_energy_eV =
        reconstructedMeanEnergyEV(edges, f, reference_eepf);
  else
  {
    double energy = 0.0;
    for (std::size_t i = 0; i < n; ++i)
    {
      const double lo = edges[i], hi = edges[i+1];
      energy += f[i] * (2.0 / 5.0) * (std::pow(hi, 2.5) - std::pow(lo, 2.5));
    }
    out.distribution.mean_energy_eV = energy;
  }
  out.growth = evaluateGrowthOnFrozenEepf(input, out.distribution,
                                          ionizations, attachments, reference_eepf);
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
