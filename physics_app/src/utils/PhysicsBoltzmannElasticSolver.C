#include "PhysicsBoltzmannElasticSolver.h"

#include <algorithm>
#include <cmath>
#include <limits>
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

Coefficients atFace(const ElasticInput & input, double energy)
{
  double sigma_m = 0.0;
  double sigma_e = 0.0;
  for (const auto & target : input.targets)
  {
    const double sigma = target.mole_fraction * interpolate(target, energy);
    sigma_m += sigma;
    sigma_e += 2.0 * target.electron_mass_ratio * sigma;
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
} // namespace PhysicsBoltzmann
