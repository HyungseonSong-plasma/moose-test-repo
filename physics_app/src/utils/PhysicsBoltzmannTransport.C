#include "PhysicsBoltzmannTransport.h"
#include "PhysicsBoltzmannEnergyMesh.h"

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

double interpolate(const std::vector<double> & energy,
                   const std::vector<double> & sigma, double e)
{
  const auto it = std::upper_bound(energy.begin(), energy.end(), e);
  if (it == energy.begin())
    return sigma.front();
  if (it == energy.end())
    return sigma.back();
  const std::size_t right = static_cast<std::size_t>(it - energy.begin());
  const std::size_t left = right - 1;
  const double alpha = (e - energy[left]) / (energy[right] - energy[left]);
  return (1.0 - alpha) * sigma[left] + alpha * sigma[right];
}

double interpolate(const ElasticTarget & t, double e)
{
  return interpolate(t.energy_eV, t.momentum_transfer_m2, e);
}

double excitationAt(const ExcitationChannel & channel, double e)
{
  const auto & energy = channel.energy_eV;
  const auto & sigma = channel.cross_section_m2;
  const auto upper = std::upper_bound(energy.begin(), energy.end(), e);
  if (upper == energy.begin())
    return sigma.front();
  if (upper == energy.end())
    return sigma.back();
  const auto j = static_cast<std::size_t>(upper - energy.begin());
  const double alpha = (e - energy[j - 1]) / (energy[j] - energy[j - 1]);
  return (1.0 - alpha) * sigma[j - 1] + alpha * sigma[j];
}
} // namespace

ElasticTransportMoments evaluateExcitationTransportMoments(
    const ElasticInput & input,
    const ElasticResult & distribution,
    const std::vector<ExcitationChannel> & excitations)
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
        (!t.field_momentum_transfer_m2.empty() &&
         t.field_momentum_transfer_m2.size() != t.energy_eV.size()) ||
        t.energy_eV.front() > 0.0 || t.energy_eV.back() < input.max_energy_eV)
      throw std::invalid_argument("Boltzmann M7: invalid elastic collision table");
    fractions += t.mole_fraction;
    for (std::size_t i = 0; i < t.energy_eV.size(); ++i)
      if (!std::isfinite(t.energy_eV[i]) || !std::isfinite(t.momentum_transfer_m2[i]) ||
          t.momentum_transfer_m2[i] < 0.0 ||
          (!t.field_momentum_transfer_m2.empty() &&
           (!std::isfinite(t.field_momentum_transfer_m2[i]) ||
            t.field_momentum_transfer_m2[i] < 0.0)) ||
          (i && !(t.energy_eV[i] > t.energy_eV[i - 1])))
        throw std::invalid_argument("Boltzmann M7: invalid momentum cross-section interpolation");
  }
  if (std::abs(fractions - 1.0) > 1e-12)
    throw std::invalid_argument("Boltzmann M7: target fractions must sum to one");
  // Validate all represented excitation channels before adding their
  // total scattering cross sections to the first-angular-moment collision
  // frequency. ELASTIC momentum cross sections must exclude these channels.
  for (const auto & ch : excitations)
  {
    if (ch.name.empty() || ch.target_name.empty() ||
        !(std::isfinite(ch.threshold_eV) && ch.threshold_eV > 0.0 &&
          ch.threshold_eV < input.max_energy_eV) ||
        ch.energy_eV.size() < 2 ||
        ch.cross_section_m2.size() != ch.energy_eV.size() ||
        ch.energy_eV.front() > 0.0 ||
        ch.energy_eV.back() < input.max_energy_eV)
      throw std::invalid_argument("Boltzmann M7b: incomplete excitation threshold or table");
    for (std::size_t j = 0; j < ch.energy_eV.size(); ++j)
      if (!std::isfinite(ch.energy_eV[j]) ||
          !std::isfinite(ch.cross_section_m2[j]) ||
          ch.energy_eV[j] < 0.0 || ch.cross_section_m2[j] < 0.0 ||
          (j && !(ch.energy_eV[j] > ch.energy_eV[j - 1])))
        throw std::invalid_argument("Boltzmann M7b: invalid inelastic cross section");
    const auto lower = std::find_if(input.targets.begin(), input.targets.end(),
        [&ch](const ElasticTarget & t) { return t.name == ch.target_name; });
    if (lower == input.targets.end())
      throw std::invalid_argument("Boltzmann M7b: excitation target missing");
    if (!ch.upper_state_target_name.empty())
    {
      const auto upper = std::find_if(input.targets.begin(), input.targets.end(),
          [&ch](const ElasticTarget & t) { return t.name == ch.upper_state_target_name; });
      if (upper == input.targets.end() || ch.upper_state_target_name == ch.target_name ||
          !(std::isfinite(ch.upper_to_lower_weight_ratio) &&
            ch.upper_to_lower_weight_ratio > 0.0))
        throw std::invalid_argument("Boltzmann M7b: superelastic state or degeneracy invalid");
    }
    else if (ch.upper_to_lower_weight_ratio != 1.0)
      throw std::invalid_argument("Boltzmann M7b: reverse ratio without upper target");
  }
  const auto sigma_m = [&](double energy)
  {
    double value = 0.0;
    for (const auto & target : input.targets)
      value += target.mole_fraction *
          (target.field_momentum_transfer_m2.empty() ?
           interpolate(target, energy) :
           interpolate(target.energy_eV,
                       target.field_momentum_transfer_m2, energy));
    for (const auto & ch : excitations)
    {
      const auto lower = std::find_if(input.targets.begin(), input.targets.end(),
          [&ch](const ElasticTarget & t) { return t.name == ch.target_name; });
      // When full source scattering is already in field_momentum, never
      // add this excitation again. This preserves M7b behavior for classic
      // ELASTIC inputs with no supplied complete first-harmonic table.
      if (energy >= ch.threshold_eV &&
          lower->field_momentum_transfer_m2.empty())
        value += lower->mole_fraction * excitationAt(ch, energy);
      if (!ch.upper_state_target_name.empty() &&
          energy > 0.0 && energy + ch.threshold_eV <= input.max_energy_eV)
      {
        const auto upper = std::find_if(input.targets.begin(), input.targets.end(),
            [&ch](const ElasticTarget & t) { return t.name == ch.upper_state_target_name; });
        value += upper->mole_fraction / ch.upper_to_lower_weight_ratio *
                 ((energy + ch.threshold_eV) / energy) *
                 excitationAt(ch, energy + ch.threshold_eV);
      }
    }
    if (!(std::isfinite(value) && value > 0.0))
      throw std::invalid_argument("Boltzmann M7: total momentum-transfer cross section must be positive");
    return value;
  };
  const auto edges = energyMeshEdges(input);
  const auto centers = energyMeshCenters(edges);
  const auto & f = distribution.eepf_eV_minus_3_halves;
  double normalization = 0.0, mean_energy = 0.0;
  double max_f = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    const double lo = edges[i], hi = edges[i+1];
    if (!std::isfinite(f[i]) || f[i] < 0.0 ||
        !std::isfinite(distribution.energy_eV[i]) ||
        std::abs(distribution.energy_eV[i] - centers[i]) > 1e-9 * (hi - lo))
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
    const double width = edges[i+1]-edges[i];
    const double mid = centers[i];
    for (std::size_t q = 0; q < 4; ++q)
    {
      const double e = mid + 0.5 * width * nodes[q];
      const double contribution = 0.5 * width * weights[q] * f[i] * e / sigma_m(e);
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
    const double e = edges[i];
    const double jump = (f[i - 1] - f[i]) / sigma_m(e);
    mobility_moment += e * jump;
    energy_mobility_moment += e * e * jump;
  }
  const double upper = input.max_energy_eV;
  const double boundary = f.back() / sigma_m(upper);
  mobility_moment += upper * boundary;
  energy_mobility_moment += upper * upper * boundary;

  // BOLSIG+ 07/2024 f1^Re and f1^Im, using RMS E/N. q is the
  // reduced angular frequency (omega/N) and Q is total scattering m².
  // f1^Re = EN * Q/(Q²+q_e²) * df0/de
  // f1^Im = EN * q_e/(Q²+q_e²) * df0/de,
  // where q_e = (omega/N)/(gamma*sqrt(e)) in m².
  // Keep AC real/imag coefficients DISTINCT from the DC mobility.
  const double reduced_omega = input.reduced_angular_frequency_m3_per_s;
  if (!(std::isfinite(reduced_omega) && reduced_omega >= 0.0))
    throw std::invalid_argument("Boltzmann M8: invalid reduced AC frequency");
  if (reduced_omega > 0.0)
  {
    const double gamma = 3.0 * prefactor;
    double real_moment = 0.0, imag_moment = 0.0;
    for (std::size_t i = 1; i < n; ++i)
    {
      const double e = edges[i];
      const double Q = sigma_m(e);
      const double qe_ac = reduced_omega / (gamma * std::sqrt(e));
      const double denom = Q*Q + qe_ac*qe_ac;
      const double delta = e * (f[i-1]-f[i]);
      real_moment += delta * Q / denom;
      imag_moment += delta * qe_ac / denom;
    }
    const double e = edges.back();
    const double Q = sigma_m(e);
    const double qe_ac = reduced_omega / (gamma * std::sqrt(e));
    const double denom = Q*Q + qe_ac*qe_ac;
    real_moment += e * f.back() * Q / denom;
    imag_moment += e * f.back() * qe_ac / denom;
    out.ac_real_mobility_N_per_m_V_s = prefactor * real_moment;
    out.ac_imag_mobility_N_per_m_V_s = prefactor * imag_moment;
    if (!(std::isfinite(out.ac_real_mobility_N_per_m_V_s) &&
          out.ac_real_mobility_N_per_m_V_s >= 0.0 &&
          std::isfinite(out.ac_imag_mobility_N_per_m_V_s) &&
          out.ac_imag_mobility_N_per_m_V_s >= 0.0))
      throw std::runtime_error("Boltzmann M8: nonphysical AC mobility components");
  }

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
ElasticTransportMoments evaluateElasticTransportMoments(
    const ElasticInput & input, const ElasticResult & distribution)
{
  return evaluateExcitationTransportMoments(input, distribution, {});
}
} // namespace PhysicsBoltzmann
