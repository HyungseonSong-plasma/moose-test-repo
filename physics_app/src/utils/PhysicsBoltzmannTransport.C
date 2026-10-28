#include "PhysicsBoltzmannTransport.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace PhysicsBoltzmann
{
namespace
{
constexpr double qe = 1.602176634e-19;
constexpr double me = 9.1093837139e-31;
const double prefactor = std::sqrt(2.0 * qe / me) / 3.0;

double interpolate(const ElasticTarget & t, double e)
{
  const auto it = std::upper_bound(t.energy_eV.begin(), t.energy_eV.end(), e);
  if (it == t.energy_eV.begin())
    return t.momentum_transfer_m2.front();
  if (it == t.energy_eV.end())
    return t.momentum_transfer_m2.back();
  const std::size_t right = static_cast<std::size_t>(it - t.energy_eV.begin());
  const std::size_t left = right - 1;
  const double alpha = (e - t.energy_eV[left]) /
                       (t.energy_eV[right] - t.energy_eV[left]);
  return (1.0 - alpha) * t.momentum_transfer_m2[left] +
         alpha * t.momentum_transfer_m2[right];
}
} // namespace

ElasticTransportMoments evaluateElasticTransportMoments(
    const ElasticInput & input,
    const ElasticResult & distribution)
{
  const std::size_t n = input.cells;
  if (n < 2 || n > 16384 || !(std::isfinite(input.max_energy_eV) &&
                              input.max_energy_eV > 0.0) ||
      input.targets.empty() || distribution.energy_eV.size() != n ||
      distribution.eepf_eV_minus_3_halves.size() != n)
    throw std::invalid_argument("Boltzmann M7: invalid energy grid or EEPF dimensions");
  double fractions = 0.0;
  for (const auto & t : input.targets)
  {
    if (!(std::isfinite(t.mole_fraction) && t.mole_fraction > 0.0) ||
        t.energy_eV.size() < 2 || t.momentum_transfer_m2.size() != t.energy_eV.size() ||
        t.energy_eV.front() > 0.0 || t.energy_eV.back() < input.max_energy_eV)
      throw std::invalid_argument("Boltzmann M7: invalid elastic collision table");
    fractions += t.mole_fraction;
    for (std::size_t i = 0; i < t.energy_eV.size(); ++i)
      if (!std::isfinite(t.energy_eV[i]) || !std::isfinite(t.momentum_transfer_m2[i]) ||
          t.momentum_transfer_m2[i] < 0.0 ||
          (i && !(t.energy_eV[i] > t.energy_eV[i - 1])))
        throw std::invalid_argument("Boltzmann M7: invalid momentum cross-section interpolation");
  }
  if (std::abs(fractions - 1.0) > 1e-12)
    throw std::invalid_argument("Boltzmann M7: target fractions must sum to one");
  const auto sigma_m = [&](double energy)
  {
    double value = 0.0;
    for (const auto & target : input.targets)
      value += target.mole_fraction * interpolate(target, energy);
    if (!(std::isfinite(value) && value > 0.0))
      throw std::invalid_argument("Boltzmann M7: total momentum-transfer cross section must be positive");
    return value;
  };
  const double h = input.max_energy_eV / n;
  const auto & f = distribution.eepf_eV_minus_3_halves;
  double normalization = 0.0, mean_energy = 0.0;
  double max_f = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    const double lo = i * h, hi = (i + 1) * h;
    if (!std::isfinite(f[i]) || f[i] < 0.0 ||
        !std::isfinite(distribution.energy_eV[i]) ||
        std::abs(distribution.energy_eV[i] - (i + 0.5) * h) > 1e-9 * h)
      throw std::invalid_argument("Boltzmann M7: invalid EEPF/energy centers");
    normalization += f[i] * (2.0 / 3.0) *
                     (std::pow(hi, 1.5) - std::pow(lo, 1.5));
    mean_energy += f[i] * (2.0 / 5.0) *
                   (std::pow(hi, 2.5) - std::pow(lo, 2.5));
    max_f = std::max(max_f, f[i]);
  }
  if (!(max_f > 0.0 && std::abs(normalization - 1.0) < 1e-8 &&
        std::isfinite(distribution.mean_energy_eV) &&
        distribution.mean_energy_eV > 0.0 &&
        std::abs(mean_energy - distribution.mean_energy_eV) /
            distribution.mean_energy_eV < 1e-8))
    throw std::invalid_argument("Boltzmann M7: EEPF mass/moment consistency failed");

  ElasticTransportMoments out;
  out.high_energy_tail_ratio = f.back() / max_f;
  if (out.high_energy_tail_ratio > 1e-3)
    throw std::invalid_argument("Boltzmann M7: high-energy EEPF tail not resolved; enlarge emax");

  // Gauss-Legendre quadrature on every cell for the non-Maxwellian diffusion
  // moments. Gaussian 4-point integration is exact for polynomial integrands
  // through order 7. Smooth variable-cross-section integrands are accurately
  // approximated but require independent energy-grid convergence.
  const double nodes[4] = {-0.8611363115940526, -0.3399810435848563,
                           0.3399810435848563, 0.8611363115940526};
  const double weights[4] = {0.3478548451374539, 0.6521451548625461,
                             0.6521451548625461, 0.3478548451374539};
  double diff_moment = 0.0, diff_energy_moment = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    const double mid = (i + 0.5) * h;
    for (std::size_t q = 0; q < 4; ++q)
    {
      const double e = mid + 0.5 * h * nodes[q];
      const double contribution = 0.5 * h * weights[q] * f[i] * e / sigma_m(e);
      diff_moment += contribution;
      diff_energy_moment += contribution * e;
    }
  }

  // Distributional derivative of piecewise-constant f0: its jumps are
  // located on cell interfaces. The endpoint f(emax)->0 contribution is
  // explicit, and high-energy tail resolution is checked above.
  double mobility_moment = 0.0, energy_mobility_moment = 0.0;
  for (std::size_t i = 1; i < n; ++i)
  {
    const double e = i * h;
    const double jump = (f[i - 1] - f[i]) / sigma_m(e);
    mobility_moment += e * jump;
    energy_mobility_moment += e * e * jump;
  }
  const double upper = input.max_energy_eV;
  const double boundary = f.back() / sigma_m(upper);
  mobility_moment += upper * boundary;
  energy_mobility_moment += upper * upper * boundary;

  out.reduced_mobility_N_per_m_V_s = prefactor * mobility_moment;
  out.reduced_diffusion_N_per_m_s = prefactor * diff_moment;
  out.reduced_energy_mobility_N_per_m_V_s =
      prefactor * energy_mobility_moment / mean_energy;
  out.reduced_energy_diffusion_N_per_m_s =
      prefactor * diff_energy_moment / mean_energy;

  if (!(std::isfinite(out.reduced_mobility_N_per_m_V_s) &&
        out.reduced_mobility_N_per_m_V_s > 0.0 &&
        std::isfinite(out.reduced_diffusion_N_per_m_s) &&
        out.reduced_diffusion_N_per_m_s > 0.0 &&
        std::isfinite(out.reduced_energy_mobility_N_per_m_V_s) &&
        out.reduced_energy_mobility_N_per_m_V_s > 0.0 &&
        std::isfinite(out.reduced_energy_diffusion_N_per_m_s) &&
        out.reduced_energy_diffusion_N_per_m_s > 0.0))
    throw std::runtime_error("Boltzmann M7: nonphysical reduced electron/energy transport moment");
  return out;
}
} // namespace PhysicsBoltzmann
