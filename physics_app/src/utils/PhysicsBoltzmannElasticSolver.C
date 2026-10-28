#include "PhysicsBoltzmannElasticSolver.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <utility>
#include <numeric>
#include <stdexcept>

namespace PhysicsBoltzmann
{
namespace
{
constexpr double electron_charge_C = 1.602176634e-19;
constexpr double electron_mass_kg = 9.1093837139e-31;
constexpr double boltzmann_J_per_K = 1.380649e-23;
constexpr double townsend_V_m2 = 1e-21;

bool finiteNonnegative(double v) { return std::isfinite(v) && v >= 0.0; }
bool finitePositive(double v) { return std::isfinite(v) && v > 0.0; }

void validate(const ElasticInput & input)
{
  if (!finiteNonnegative(input.reduced_field_Td))
    throw std::invalid_argument("Boltzmann: reduced field must be finite and nonnegative");
  if (!finitePositive(input.gas_temperature_K) || !finitePositive(input.max_energy_eV))
    throw std::invalid_argument("Boltzmann: gas temperature and max energy must be positive");
  if (input.cells < 2 || input.cells > 1000000)
    throw std::invalid_argument("Boltzmann: energy cell count outside [2, 1000000]");
  if (input.targets.empty())
    throw std::invalid_argument("Boltzmann: at least one elastic target is required");

  double sum = 0.0;
  for (const auto & target : input.targets)
  {
    if (target.name.empty() || !finitePositive(target.mole_fraction) ||
        !finitePositive(target.electron_mass_ratio) || target.electron_mass_ratio >= 1.0)
      throw std::invalid_argument("Boltzmann: invalid target name, fraction or electron/mass ratio");
    const auto n = target.energy_eV.size();
    if (n < 2 || target.momentum_transfer_m2.size() != n)
      throw std::invalid_argument("Boltzmann: cross-section table lengths mismatch");
    for (std::size_t k = 0; k < n; ++k)
    {
      if (!finiteNonnegative(target.energy_eV[k]) ||
          !finiteNonnegative(target.momentum_transfer_m2[k]))
        throw std::invalid_argument("Boltzmann: non-finite/negative cross-section datum");
      if (k && !(target.energy_eV[k] > target.energy_eV[k - 1]))
        throw std::invalid_argument("Boltzmann: cross-section energies must increase strictly");
    }
    if (target.energy_eV.front() > 0.0 || target.energy_eV.back() < input.max_energy_eV)
      throw std::invalid_argument("Boltzmann: cross-section domain does not cover energy grid");
    sum += target.mole_fraction;
  }
  if (std::abs(sum - 1.0) > 1e-12)
    throw std::invalid_argument("Boltzmann: elastic target mole fractions must sum to 1");
}

double interpolate(const ElasticTarget & target, double energy)
{
  const auto upper = std::upper_bound(target.energy_eV.begin(), target.energy_eV.end(), energy);
  if (upper == target.energy_eV.begin())
    return target.momentum_transfer_m2.front();
  if (upper == target.energy_eV.end())
    return target.momentum_transfer_m2.back();
  const std::size_t right = static_cast<std::size_t>(upper - target.energy_eV.begin());
  const std::size_t left = right - 1;
  const double t = (energy - target.energy_eV[left]) /
                   (target.energy_eV[right] - target.energy_eV[left]);
  return (1.0 - t) * target.momentum_transfer_m2[left] +
         t * target.momentum_transfer_m2[right];
}

// Numerically stable Bernoulli function B(x) = x/(exp(x)-1).
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

struct Coefficients { double W; double D; };

Coefficients atFace(const ElasticInput & input, double energy,
                    const std::vector<ExcitationChannel> * channels = nullptr)
{
  double sigma_m = 0.0;
  double sigma_e = 0.0;
  for (const auto & target : input.targets)
  {
    const double sigma = target.mole_fraction * interpolate(target, energy);
    sigma_m += sigma;
    sigma_e += 2.0 * target.electron_mass_ratio * sigma;
  }
  // Isotropic inelastic scattering also relaxes the first angular moment.
  // sigma_m below is ELASTIC momentum-transfer plus all active excitation
  // total cross sections (NOT an already-inclusive EFFECTIVE elastic sigma).
  if (channels)
    for (const auto & channel : *channels)
    {
      const auto xsAt = [&channel](double e)
      {
        const auto upper = std::upper_bound(channel.energy_eV.begin(), channel.energy_eV.end(), e);
        const std::size_t right = upper == channel.energy_eV.end()
                                      ? channel.energy_eV.size() - 1
                                      : static_cast<std::size_t>(upper - channel.energy_eV.begin());
        const std::size_t left = right == 0 ? 0 : right - 1;
        return left == right ? channel.cross_section_m2[left]
            : channel.cross_section_m2[left] +
              (e - channel.energy_eV[left]) *
              (channel.cross_section_m2[right] - channel.cross_section_m2[left]) /
              (channel.energy_eV[right] - channel.energy_eV[left]);
      };
      const auto lower = std::find_if(input.targets.begin(), input.targets.end(),
          [&channel](const ElasticTarget & t) { return t.name == channel.target_name; });
      if (lower == input.targets.end())
        throw std::invalid_argument("Boltzmann: excitation momentum target is missing");
      if (energy >= channel.threshold_eV)
        sigma_m += lower->mole_fraction * xsAt(energy);
      if (!channel.upper_state_target_name.empty() &&
          energy + channel.threshold_eV <= input.max_energy_eV)
      {
        const auto upper = std::find_if(input.targets.begin(), input.targets.end(),
            [&channel](const ElasticTarget & t) { return t.name == channel.upper_state_target_name; });
        if (upper == input.targets.end())
          throw std::invalid_argument("Boltzmann: superelastic momentum target is missing");
        // Klein-Rosseland microreversibility:
        // sigma_inverse(e) = (g_lower/g_upper)*(e+u)/e*sigma_forward(e+u).
        sigma_m += upper->mole_fraction / channel.upper_to_lower_weight_ratio *
                   ((energy + channel.threshold_eV) / energy) *
                   xsAt(energy + channel.threshold_eV);
      }
    }
  if (!finitePositive(sigma_m) || !finitePositive(sigma_e))
    throw std::invalid_argument("Boltzmann: total elastic momentum cross section vanishes at an interior face");

  // Hagelaar & Pitchford 2005, energy-space two-term elastic coefficients.
  // f0 is the EEPF (not the energy PDF); coefficients are reduced by neutral N.
  const double gamma = std::sqrt(2.0 * electron_charge_C / electron_mass_kg);
  const double theta = boltzmann_J_per_K * input.gas_temperature_K / electron_charge_C;
  const double EN = input.reduced_field_Td * townsend_V_m2;
  const double W = -gamma * energy * energy * sigma_e;
  const double D = gamma * ((EN * EN / 3.0) * energy / sigma_m +
                            theta * energy * energy * sigma_e);
  if (!finitePositive(D) || !std::isfinite(W))
    throw std::invalid_argument("Boltzmann: invalid energy-space transport coefficient");
  return {W, D};
}
} // namespace

ElasticResult solveElasticSteadyState(const ElasticInput & input)
{
  validate(input);
  ElasticResult result;
  const std::size_t n = input.cells;
  const double h = input.max_energy_eV / static_cast<double>(n);
  result.energy_eV.resize(n);
  result.eepf_eV_minus_3_halves.resize(n);

  // Tridiagonal steady conservative operator with zero flux at both ends:
  // J_{i+1/2} = D/h [B(-P)f_i - B(P)f_{i+1}], P=W*h/D.
  // Its nullspace can be obtained without a singular sparse-matrix solve:
  // J=0 => log(f_{i+1}/f_i)=P. This is exact for the discrete SG flux.
  std::vector<double> log_f(n, 0.0);
  double maximum_log = 0.0;
  for (std::size_t i = 0; i < n; ++i)
    result.energy_eV[i] = (static_cast<double>(i) + 0.5) * h;
  for (std::size_t i = 1; i < n; ++i)
  {
    const auto c = atFace(input, static_cast<double>(i) * h);
    log_f[i] = log_f[i - 1] + c.W * h / c.D;
    maximum_log = std::max(maximum_log, log_f[i]);
  }
  for (std::size_t i = 0; i < n; ++i)
    result.eepf_eV_minus_3_halves[i] = std::exp(log_f[i] - maximum_log);

  // Cell-integrated sqrt(e) moments avoid a center-point quadrature
  // singularity at e=0 and preserve the meaning of the EEPF normalization.
  double total = 0.0;
  double moment1 = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    const double left = i * h, right = (i + 1) * h;
    const double zeroth = (2.0 / 3.0) * (std::pow(right, 1.5) - std::pow(left, 1.5));
    const double first = (2.0 / 5.0) * (std::pow(right, 2.5) - std::pow(left, 2.5));
    total += result.eepf_eV_minus_3_halves[i] * zeroth;
    moment1 += result.eepf_eV_minus_3_halves[i] * first;
  }
  if (!finitePositive(total) || !std::isfinite(moment1))
    throw std::runtime_error("Boltzmann: failed to normalize elastic EEPF");

  for (auto & f : result.eepf_eV_minus_3_halves)
    f /= total;
  result.normalization = 1.0;
  result.mean_energy_eV = moment1 / total;

  // Cancellation-safe normalized interface-flux residual. No-finite-flux
  // requirement means all interfaces must satisfy the conservative stencil.
  for (std::size_t i = 1; i < n; ++i)
  {
    const auto c = atFace(input, static_cast<double>(i) * h);
    const double p = c.W * h / c.D;
    const double left = bernoulli(-p) * result.eepf_eV_minus_3_halves[i - 1];
    const double right = bernoulli(p) * result.eepf_eV_minus_3_halves[i];
    const double denominator = std::abs(left) + std::abs(right);
    if (denominator > 1e-250)
      result.maximum_normalized_flux_residual = std::max(
          result.maximum_normalized_flux_residual,
          std::abs(left - right) / denominator);
  }
  if (!std::isfinite(result.mean_energy_eV) ||
      !std::isfinite(result.maximum_normalized_flux_residual))
    throw std::runtime_error("Boltzmann: non-finite solution diagnostic");
  return result;
}

namespace
{
// Exact integral of epsilon * sigma(epsilon) for a piecewise-linear cross section.
// The threshold is treated as a hard physical gate, not a smooth extrapolation.
double weightedExcitationIntegral(const ExcitationChannel & channel, double a, double b)
{
  a = std::max(a, channel.threshold_eV);
  if (b <= a)
    return 0.0;
  const auto & x = channel.energy_eV;
  const auto & y = channel.cross_section_m2;
  double total = 0.0;
  while (a < b)
  {
    const auto upper = std::upper_bound(x.begin(), x.end(), a);
    std::size_t k = upper == x.begin() ? 0 : static_cast<std::size_t>(upper - x.begin() - 1);
    k = std::min(k, x.size() - 2);
    const double right = std::min(b, x[k + 1]);
    if (!(right > a))
      throw std::runtime_error("Boltzmann: excitation integration segment did not advance");
    const double slope = (y[k + 1] - y[k]) / (x[k + 1] - x[k]);
    const double at_left = y[k] + slope * (a - x[k]);
    const double delta2 = right * right - a * a;
    const double delta3 = right * right * right - a * a * a;
    total += 0.5 * at_left * delta2 +
             slope * (delta3 / 3.0 - 0.5 * a * delta2);
    a = right;
  }
  return std::max(0.0, total);
}

// Simple reproducible pivoted dense reference solve. The generic nonlocal
// problem needs a scalable sparse solver in a later, separately validated cut.
std::vector<double> pivotedSolve(std::vector<std::vector<double>> a,
                                 std::vector<double> rhs)
{
  const std::size_t n = rhs.size();
  for (std::size_t k = 0; k < n; ++k)
  {
    std::size_t pivot = k;
    for (std::size_t i = k + 1; i < n; ++i)
      if (std::abs(a[i][k]) > std::abs(a[pivot][k]))
        pivot = i;
    if (!(std::abs(a[pivot][k]) > 1e-14))
      throw std::runtime_error("Boltzmann: singular or ill-conditioned excitation system");
    std::swap(a[pivot], a[k]);
    std::swap(rhs[pivot], rhs[k]);
    for (std::size_t i = k + 1; i < n; ++i)
    {
      const double factor = a[i][k] / a[k][k];
      a[i][k] = 0.0;
      for (std::size_t j = k + 1; j < n; ++j)
        a[i][j] -= factor * a[k][j];
      rhs[i] -= factor * rhs[k];
    }
  }
  std::vector<double> result(n, 0.0);
  for (std::size_t k = n; k-- > 0;)
  {
    double value = rhs[k];
    for (std::size_t j = k + 1; j < n; ++j)
      value -= a[k][j] * result[j];
    result[k] = value / a[k][k];
    if (!std::isfinite(result[k]))
      throw std::runtime_error("Boltzmann: excitation solution contains non-finite values");
  }
  return result;
}

// Stationary conservation operator with one row pinned to f[0]=1. Its
// tridiagonal backbone is an M-matrix. A tridiagonal preconditioner is
// exact for zero excitation and cheap for nonlocal upper-energy transfers.
// We use left-preconditioned BiCGSTAB; any failure is reported, not silently
// replaced by a lower-resolution or Maxwellian approximation.
std::pair<std::vector<double>, std::size_t>
sparseBicgstabSolve(const std::vector<std::map<std::size_t, double>> & rows)
{
  const std::size_t n = rows.size();
  using Entry = std::pair<std::size_t, double>;
  std::vector<std::vector<Entry>> normalized(n);
  std::vector<double> lower(n, 0.0), upper(n, 0.0), pivot(n, 0.0), cp(n, 0.0);
  normalized[0].push_back({0, 1.0});
  for (std::size_t i = 1; i < n; ++i)
  {
    const auto diagonal = rows[i].find(i);
    if (diagonal == rows[i].end() || !(diagonal->second > 0.0) ||
        !std::isfinite(diagonal->second))
      throw std::runtime_error("Boltzmann: sparse stationary operator has invalid diagonal");
    for (const auto & item : rows[i])
    {
      const double value = item.second / diagonal->second;
      if (!std::isfinite(value))
        throw std::runtime_error("Boltzmann: sparse stationary row scaling failed");
      if (value == 0.0)
        continue;
      normalized[i].push_back({item.first, value});
      if (item.first + 1 == i)
        lower[i] = value;
      else if (item.first == i + 1)
        upper[i] = value;
    }
  }

  // Factor the tridiagonal (elastic transport + local collision loss) once.
  pivot[0] = 1.0;
  cp[0] = 0.0;
  for (std::size_t i = 1; i < n; ++i)
  {
    pivot[i] = 1.0 - lower[i] * cp[i - 1];
    if (!(pivot[i] > 0.0) || !std::isfinite(pivot[i]))
      throw std::runtime_error("Boltzmann: tridiagonal preconditioner breakdown");
    cp[i] = upper[i] / pivot[i];
  }

  const auto triSolve = [&](const std::vector<double> & b)
  {
    std::vector<double> x(n);
    x[0] = b[0];
    for (std::size_t i = 1; i < n; ++i)
      x[i] = (b[i] - lower[i] * x[i - 1]) / pivot[i];
    for (std::size_t i = n - 1; i-- > 0;)
      x[i] -= cp[i] * x[i + 1];
    return x;
  };
  const auto preconditionedApply = [&](const std::vector<double> & x)
  {
    std::vector<double> y(n, 0.0);
    for (std::size_t i = 0; i < n; ++i)
      for (const auto & [j, value] : normalized[i])
        y[i] += value * x[j];
    return triSolve(y);
  };
  const auto dot = [&](const std::vector<double> & a, const std::vector<double> & b)
  {
    double result = 0.0;
    for (std::size_t i = 0; i < n; ++i)
      result += a[i] * b[i];
    return result;
  };
  std::vector<double> source(n, 0.0);
  source[0] = 1.0;
  const auto b = triSolve(source);
  const double norm_b = std::sqrt(dot(b, b));
  if (!(norm_b > 0.0) || !std::isfinite(norm_b))
    throw std::runtime_error("Boltzmann: invalid preconditioned sparse source");

  std::vector<double> x(n, 0.0), r = b, shadow = b;
  std::vector<double> p(n, 0.0), v(n, 0.0);
  double rho_prev = 1.0, alpha = 1.0, omega = 1.0;
  constexpr std::size_t max_iterations = 400;
  constexpr double tolerance = 1e-11;
  std::size_t iterations = 0;
  bool converged = false;

  for (std::size_t iter = 0; iter < max_iterations; ++iter)
  {
    const double rho = dot(shadow, r);
    if (!std::isfinite(rho) || std::abs(rho) < 1e-30)
      throw std::runtime_error("Boltzmann: sparse BiCGSTAB rho breakdown");
    if (iter == 0)
      p = r;
    else
    {
      if (std::abs(omega) < 1e-30)
        throw std::runtime_error("Boltzmann: sparse BiCGSTAB omega breakdown");
      const double beta = (rho / rho_prev) * (alpha / omega);
      for (std::size_t i = 0; i < n; ++i)
        p[i] = r[i] + beta * (p[i] - omega * v[i]);
    }
    v = preconditionedApply(p);
    const double denominator = dot(shadow, v);
    if (!std::isfinite(denominator) || std::abs(denominator) < 1e-30)
      throw std::runtime_error("Boltzmann: sparse BiCGSTAB alpha breakdown");
    alpha = rho / denominator;
    std::vector<double> intermediate(n);
    for (std::size_t i = 0; i < n; ++i)
      intermediate[i] = r[i] - alpha * v[i];

    if (std::sqrt(dot(intermediate, intermediate)) <= tolerance * norm_b)
    {
      for (std::size_t i = 0; i < n; ++i)
        x[i] += alpha * p[i];
      iterations = iter + 1;
      converged = true;
      break;
    }
    auto t = preconditionedApply(intermediate);
    const double t2 = dot(t, t);
    if (!std::isfinite(t2) || t2 < 1e-30)
      throw std::runtime_error("Boltzmann: sparse BiCGSTAB t breakdown");
    omega = dot(t, intermediate) / t2;
    for (std::size_t i = 0; i < n; ++i)
    {
      x[i] += alpha * p[i] + omega * intermediate[i];
      r[i] = intermediate[i] - omega * t[i];
    }
    iterations = iter + 1;
    if (std::sqrt(dot(r, r)) <= tolerance * norm_b)
    {
      converged = true;
      break;
    }
    rho_prev = rho;
  }
  if (!converged)
    throw std::runtime_error("Boltzmann: sparse BiCGSTAB failed to converge in 400 iterations");

  // Validate an explicit residual; recursively updated Krylov residuals
  // alone are not authoritative on an ill-conditioned energy grid.
  const auto ax = preconditionedApply(x);
  std::vector<double> error(n);
  for (std::size_t i = 0; i < n; ++i)
    error[i] = b[i] - ax[i];
  if (!(std::sqrt(dot(error, error)) <= 1e-9 * norm_b))
    throw std::runtime_error("Boltzmann: sparse BiCGSTAB true residual failed");
  if (!std::all_of(x.begin(), x.end(), [](double z) { return std::isfinite(z); }))
    throw std::runtime_error("Boltzmann: non-finite sparse solution");
  return {x, iterations};
}
} // namespace

ConservativeExcitationOperator assembleExcitationConservativeOperator(
    const ElasticInput & input, const std::vector<ExcitationChannel> & channels)
{
  validate(input);
  if (channels.empty())
    throw std::invalid_argument("Boltzmann: at least one excitation channel is required");
  if (input.cells > 16384)
    throw std::invalid_argument("Boltzmann: excitation operator exceeds supported energy cell limit");

  std::vector<double> fractions;
  fractions.reserve(channels.size());
  std::vector<std::string> channel_names;
  for (const auto & channel : channels)
  {
    if (channel.name.empty() || channel.target_name.empty() ||
        !finitePositive(channel.threshold_eV) ||
        !(channel.threshold_eV < input.max_energy_eV))
      throw std::invalid_argument("Boltzmann: invalid excitation name/threshold");
    if (std::find(channel_names.begin(), channel_names.end(), channel.name) !=
        channel_names.end())
      throw std::invalid_argument("Boltzmann: duplicate excitation channel name");
    channel_names.push_back(channel.name);
    const auto n = channel.energy_eV.size();
    if (n < 2 || n != channel.cross_section_m2.size() ||
        channel.energy_eV.front() > 0.0 ||
        channel.energy_eV.back() < input.max_energy_eV)
      throw std::invalid_argument("Boltzmann: excitation cross section lacks full energy coverage");
    for (std::size_t k = 0; k < n; ++k)
    {
      if (!finiteNonnegative(channel.energy_eV[k]) ||
          !finiteNonnegative(channel.cross_section_m2[k]) ||
          (k && !(channel.energy_eV[k] > channel.energy_eV[k - 1])))
        throw std::invalid_argument("Boltzmann: invalid excitation cross section table");
    }
    const auto target = std::find_if(input.targets.begin(), input.targets.end(),
        [&channel](const ElasticTarget & t) { return t.name == channel.target_name; });
    if (target == input.targets.end())
      throw std::invalid_argument("Boltzmann: excitation target is not in elastic mixture");
    fractions.push_back(target->mole_fraction);
    if (!channel.upper_state_target_name.empty())
    {
      if (channel.upper_state_target_name == channel.target_name ||
          !finitePositive(channel.upper_to_lower_weight_ratio))
        throw std::invalid_argument("Boltzmann: invalid superelastic upper state or degeneracy ratio");
      const auto upper = std::find_if(input.targets.begin(), input.targets.end(),
          [&channel](const ElasticTarget & t) { return t.name == channel.upper_state_target_name; });
      if (upper == input.targets.end())
        throw std::invalid_argument("Boltzmann: superelastic target requires explicit elastic data and population");
    }
    else if (channel.upper_to_lower_weight_ratio != 1.0)
      throw std::invalid_argument("Boltzmann: degeneracy ratio without a superelastic target");
  }

  const std::size_t n = input.cells;
  const double h = input.max_energy_eV / static_cast<double>(n);
  const double gamma = std::sqrt(2.0 * electron_charge_C / electron_mass_kg);
  std::vector<std::map<std::size_t, double>> a(n);
  std::vector<double> weight(n, 0.0);
  for (std::size_t i = 0; i < n; ++i)
  {
    const double left = static_cast<double>(i) * h;
    const double right = left + h;
    weight[i] = (2.0 / 3.0) * (std::pow(right, 1.5) - std::pow(left, 1.5));
  }

  // Divergence of the same conservative elastic SG interface flux as M1.
  for (std::size_t i = 1; i < n; ++i)
  {
    const auto face = atFace(input, static_cast<double>(i) * h, &channels);
    const double p = face.W * h / face.D;
    const double left = face.D / h * bernoulli(-p);
    const double right = face.D / h * bernoulli(p);
    a[i - 1][i - 1] += left;
    a[i - 1][i] -= right;
    a[i][i - 1] -= left;
    a[i][i] += right;
  }

  double maximum_balance_error = 0.0;
  // A = div(J) - S, where S = gain - loss. Each excitation donor
  // transfers epsilon -> epsilon-u; overlap integrals are deposited into
  // the correct destination energy cells (no nearest-cell shortcut).
  for (std::size_t c = 0; c < channels.size(); ++c)
  {
    const auto & channel = channels[c];
    const double u = channel.threshold_eV;
    const double coefficient = gamma * fractions[c];
    for (std::size_t donor = 0; donor < n; ++donor)
    {
      const double lo = std::max(static_cast<double>(donor) * h, u);
      const double hi = static_cast<double>(donor + 1) * h;
      if (hi <= lo)
        continue;
      const double total = coefficient * weightedExcitationIntegral(channel, lo, hi);
      double gains = 0.0;
      // A shifted interval of width <= h intersects at most two target cells.
      const auto first = static_cast<std::size_t>(
          std::max(0.0, std::floor((lo - u) / h)));
      const auto last = static_cast<std::size_t>(
          std::min(static_cast<double>(n - 1),
                   std::floor(std::nextafter((hi - u) / h,
                                             -std::numeric_limits<double>::infinity()))));
      for (std::size_t dest = first; dest <= last && dest < n; ++dest)
      {
        const double xlo = std::max(lo, u + static_cast<double>(dest) * h);
        const double xhi = std::min(hi, u + static_cast<double>(dest + 1) * h);
        if (xhi <= xlo)
          continue;
        const double gain = coefficient * weightedExcitationIntegral(channel, xlo, xhi);
        a[dest][donor] -= gain;
        gains += gain;
      }
      a[donor][donor] += total;
      if (total > 0.0)
        maximum_balance_error = std::max(
            maximum_balance_error, std::abs(total - gains) / total);
    }
  }
  // Excited-state collisions add energy: e -> e+u. Detailed balancing
  // evaluates the forward excitation cross section at (e+u), multiplied
  // by (g_lower/g_upper). The electron energy factor (e+u) is integrated
  // exactly with the same piecewise-linear quadrature as the forward term.
  // Only donors with e+u <= emax are admitted so no electron is deposited
  // outside the bounded energy interval; emax sensitivity is a physics gate.
  for (std::size_t c = 0; c < channels.size(); ++c)
  {
    const auto & channel = channels[c];
    if (channel.upper_state_target_name.empty())
      continue;
    const auto upper = std::find_if(input.targets.begin(), input.targets.end(),
        [&channel](const ElasticTarget & t) { return t.name == channel.upper_state_target_name; });
    const double u = channel.threshold_eV;
    const double coefficient = gamma * upper->mole_fraction /
                               channel.upper_to_lower_weight_ratio;
    for (std::size_t donor = 0; donor < n; ++donor)
    {
      const double lo = static_cast<double>(donor) * h;
      const double hi = std::min(static_cast<double>(donor + 1) * h, input.max_energy_eV - u);
      if (hi <= lo)
        continue;
      const double total = coefficient * weightedExcitationIntegral(channel, lo + u, hi + u);
      double gains = 0.0;
      const auto first = static_cast<std::size_t>(std::floor((lo + u) / h));
      const auto last = static_cast<std::size_t>(
          std::min(static_cast<double>(n - 1),
                   std::floor(std::nextafter((hi + u) / h,
                                             -std::numeric_limits<double>::infinity()))));
      for (std::size_t dest = first; dest <= last && dest < n; ++dest)
      {
        const double xlo = std::max(lo + u, static_cast<double>(dest) * h);
        const double xhi = std::min(hi + u, static_cast<double>(dest + 1) * h);
        if (xhi <= xlo)
          continue;
        const double gain = coefficient * weightedExcitationIntegral(channel, xlo, xhi);
        a[dest][donor] -= gain;
        gains += gain;
      }
      a[donor][donor] += total;
      if (total > 0.0)
        maximum_balance_error = std::max(
            maximum_balance_error, std::abs(total - gains) / total);
    }
  }
  if (maximum_balance_error > 1e-9)
    throw std::runtime_error("Boltzmann: nonlocal excitation transfer does not conserve particle number");

  ConservativeExcitationOperator result;
  result.rows = std::move(a);
  result.cell_number_mass = std::move(weight);
  result.maximum_collision_number_balance_error = maximum_balance_error;
  return result;
}

ExcitationResult solveExcitationSteadyState(const ElasticInput & input,
                                            const std::vector<ExcitationChannel> & channels,
                                            ExcitationLinearMethod method)
{
  if (method == ExcitationLinearMethod::DenseReference && input.cells > 512)
    throw std::invalid_argument("Boltzmann: dense excitation solver limited to 512 cells");
  auto assembled = assembleExcitationConservativeOperator(input, channels);
  const std::size_t n = input.cells;
  const double h = input.max_energy_eV / static_cast<double>(n);

  auto & a = assembled.rows;
  const auto & weight = assembled.cell_number_mass;
  const double maximum_balance_error = assembled.maximum_collision_number_balance_error;

  // Dense reference is retained for an independent solver-parity oracle.
  // The sparse path pins one f0 cell, then normalizes the nullspace solution.
  // Neither path changes the underlying conservative energy operator.
  double scale = 0.0;
  std::size_t nonzeros = 0;
  for (const auto & row : a)
    for (const auto & [j, value] : row)
    {
      (void)j;
      if (value != 0.0)
        ++nonzeros;
      scale = std::max(scale, std::abs(value));
    }
  if (!finitePositive(scale))
    throw std::runtime_error("Boltzmann: empty excitation operator");

  const auto selected = method == ExcitationLinearMethod::Auto ?
      (n <= 512 ? ExcitationLinearMethod::DenseReference :
                  ExcitationLinearMethod::SparseBiCGSTAB) : method;
  std::vector<double> f;
  std::size_t iterations = 0;
  if (selected == ExcitationLinearMethod::DenseReference)
  {
    std::vector<std::vector<double>> dense(n, std::vector<double>(n, 0.0));
    for (std::size_t i = 0; i + 1 < n; ++i)
      for (const auto & [j, value] : a[i])
        dense[i][j] = value / scale;
    dense[n - 1] = weight;
    std::vector<double> rhs(n, 0.0);
    rhs[n - 1] = 1.0;
    f = pivotedSolve(std::move(dense), std::move(rhs));
  }
  else if (selected == ExcitationLinearMethod::SparseBiCGSTAB)
  {
    auto solved = sparseBicgstabSolve(a);
    f = std::move(solved.first);
    iterations = solved.second;
  }
  else
    throw std::invalid_argument("Boltzmann: unknown excitation linear method");

  const double max_f = *std::max_element(f.begin(), f.end());
  if (!finitePositive(max_f))
    throw std::runtime_error("Boltzmann: excitation state has nonpositive distribution");
  for (auto & v : f)
  {
    if (v < -1e-10 * max_f)
      throw std::runtime_error("Boltzmann: excitation EEPF has negative cell population");
    v = std::max(0.0, v);
  }
  double norm = 0.0;
  double energy_moment = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    norm += weight[i] * f[i];
    const double lo = static_cast<double>(i) * h;
    const double hi = lo + h;
    energy_moment += f[i] * (2.0 / 5.0) *
                     (std::pow(hi, 2.5) - std::pow(lo, 2.5));
  }
  if (!finitePositive(norm))
    throw std::runtime_error("Boltzmann: excitation EEPF normalization failed");
  for (auto & v : f)
    v /= norm;

  ExcitationResult result;
  result.distribution.energy_eV.resize(n);
  for (std::size_t i = 0; i < n; ++i)
    result.distribution.energy_eV[i] = (i + 0.5) * h;
  result.distribution.eepf_eV_minus_3_halves = f;
  result.distribution.mean_energy_eV = energy_moment / norm;
  result.distribution.normalization = 1.0;
  // Interface fluxes are physically nonzero when excitation is active.
  result.distribution.maximum_normalized_flux_residual =
      std::numeric_limits<double>::quiet_NaN();

  // Evaluate the original, unmodified conservative balance, including the
  // omitted nullspace row, not merely the normalization-constrained solve.
  double residual = 0.0, magnitude = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    double ri = 0.0, absrow = 0.0;
    for (const auto & [j, coefficient] : a[i])
    {
      const double t = coefficient * f[j];
      ri += t;
      absrow += std::abs(t);
    }
    residual = std::max(residual, std::abs(ri));
    magnitude = std::max(magnitude, absrow);
  }
  result.maximum_normalized_equation_residual =
      magnitude > 0.0 ? residual / magnitude : 0.0;
  result.maximum_collision_number_balance_error = maximum_balance_error;
  result.assembled_nonzero_entries = nonzeros;
  result.linear_iterations = iterations;
  result.linear_method_used = selected;
  if (!(result.maximum_normalized_equation_residual <= 1e-8))
    throw std::runtime_error("Boltzmann: excitation stationary residual exceeds 1e-8");

  const auto moments = evaluateExcitationRatesOnEepf(input, result.distribution, channels);
  result.rate_coefficients_m3_per_s = moments.forward_rates_m3_per_s;
  result.superelastic_rate_coefficients_m3_per_s = moments.reverse_rates_m3_per_s;
  result.net_energy_loss_coefficients_eV_m3_per_s =
      moments.mixture_net_energy_losses_eV_m3_per_s;
  for (std::size_t i = 0; i < channels.size(); ++i)
    result.energy_loss_coefficients_eV_m3_per_s.push_back(
        channels[i].threshold_eV * moments.forward_rates_m3_per_s[i]);
  return result;
}

ExcitationRateMoments evaluateExcitationRatesOnEepf(
    const ElasticInput & input,
    const ElasticResult & distribution,
    const std::vector<ExcitationChannel> & channels)
{
  validate(input);
  const auto n = input.cells;
  if (distribution.energy_eV.size() != n ||
      distribution.eepf_eV_minus_3_halves.size() != n)
    throw std::invalid_argument("Boltzmann: rate evaluation EEPF grid differs from input");
  const double h = input.max_energy_eV / static_cast<double>(n);
  const double gamma = std::sqrt(2.0 * electron_charge_C / electron_mass_kg);
  const auto & f = distribution.eepf_eV_minus_3_halves;
  double norm = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    if (!std::isfinite(f[i]) || f[i] < 0.0 ||
        !std::isfinite(distribution.energy_eV[i]) ||
        std::abs(distribution.energy_eV[i] - (i+0.5)*h) > 1e-9*h)
      throw std::invalid_argument("Boltzmann: rate input EEPF invalid");
    norm += f[i] * (2.0 / 3.0) *
            (std::pow((i+1)*h, 1.5) - std::pow(i*h, 1.5));
  }
  if (!(std::abs(norm-1.0) < 1e-8))
    throw std::invalid_argument("Boltzmann: rate EEPF normalization invalid");

  ExcitationRateMoments result;
  for (const auto & channel : channels)
  {
    if (!(finitePositive(channel.threshold_eV) &&
          channel.threshold_eV < input.max_energy_eV) ||
        channel.energy_eV.size() < 2 ||
        channel.energy_eV.size() != channel.cross_section_m2.size() ||
        channel.energy_eV.front() > 0.0 ||
        channel.energy_eV.back() < input.max_energy_eV)
      throw std::invalid_argument("Boltzmann: rate channel threshold/coverage invalid");
    for (std::size_t j = 0; j < channel.energy_eV.size(); ++j)
      if (!finiteNonnegative(channel.energy_eV[j]) ||
          !finiteNonnegative(channel.cross_section_m2[j]) ||
          (j && !(channel.energy_eV[j] > channel.energy_eV[j-1])))
        throw std::invalid_argument("Boltzmann: invalid excitation rate cross section");
    const auto lower = std::find_if(input.targets.begin(), input.targets.end(),
        [&channel](const ElasticTarget & t){ return t.name == channel.target_name; });
    if (lower == input.targets.end())
      throw std::invalid_argument("Boltzmann: rate excitation target missing");
    double rate = 0.0;
    for (std::size_t i = 0; i < n; ++i)
    {
      const double lo = static_cast<double>(i) * h;
      rate += gamma * f[i] * weightedExcitationIntegral(channel, lo, lo+h);
    }
    double reverse_rate = 0.0;
    double upper_fraction = 0.0;
    if (!channel.upper_state_target_name.empty())
    {
      const auto upper = std::find_if(input.targets.begin(), input.targets.end(),
          [&channel](const ElasticTarget & t){return t.name == channel.upper_state_target_name;});
      if (upper == input.targets.end() ||
          !finitePositive(channel.upper_to_lower_weight_ratio))
        throw std::invalid_argument("Boltzmann: missing reverse target or invalid degeneracy");
      upper_fraction = upper->mole_fraction;
      for (std::size_t i = 0; i < n; ++i)
      {
        const double lo = i*h;
        const double hi = std::min(lo+h, input.max_energy_eV-channel.threshold_eV);
        if (hi > lo)
          reverse_rate += gamma / channel.upper_to_lower_weight_ratio * f[i] *
              weightedExcitationIntegral(channel, lo+channel.threshold_eV,
                                         hi+channel.threshold_eV);
      }
    }
    else if (channel.upper_to_lower_weight_ratio != 1.0)
      throw std::invalid_argument("Boltzmann: degeneracy without reverse target");
    result.forward_rates_m3_per_s.push_back(rate);
    result.reverse_rates_m3_per_s.push_back(reverse_rate);
    result.mixture_net_energy_losses_eV_m3_per_s.push_back(
        channel.threshold_eV * (lower->mole_fraction*rate -
                                 upper_fraction*reverse_rate));
  }
  return result;
}

} // namespace PhysicsBoltzmann
