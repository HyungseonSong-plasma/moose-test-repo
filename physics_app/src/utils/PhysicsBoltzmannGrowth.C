#include "PhysicsBoltzmannGrowth.h"
#include "PhysicsBoltzmannEnergyMesh.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>

namespace PhysicsBoltzmann
{
namespace
{
constexpr double electron_charge_C = 1.602176634e-19;
constexpr double electron_mass_kg = 9.1093837139e-31;
const double gamma = std::sqrt(2.0 * electron_charge_C / electron_mass_kg);

bool nonnegative(double x) { return std::isfinite(x) && x >= 0.0; }

double targetFraction(const ElasticInput & input, const std::string & name)
{
  const auto target = std::find_if(input.targets.begin(), input.targets.end(),
      [&name](const ElasticTarget & t) { return t.name == name; });
  if (target == input.targets.end() || !nonnegative(target->mole_fraction) ||
      target->mole_fraction == 0.0)
    throw std::invalid_argument("Boltzmann M6: channel target absent from active gas mixture");
  return target->mole_fraction;
}

void validateTable(const std::string & name,
                   const std::vector<double> & energy,
                   const std::vector<double> & sigma,
                   double ceiling)
{
  if (name.empty() || energy.size() < 2 || sigma.size() != energy.size() ||
      !nonnegative(energy.front()) || energy.front() != 0.0 ||
      energy.back() < ceiling)
    throw std::invalid_argument("Boltzmann M6: invalid process name or cross-section coverage");
  for (std::size_t k = 0; k < energy.size(); ++k)
    if (!nonnegative(energy[k]) || !nonnegative(sigma[k]) ||
        (k && !(energy[k] > energy[k - 1])))
      throw std::invalid_argument("Boltzmann M6: non-finite, negative or nonascending cross-section table");
}

double integralEnergyCrossSection(const std::vector<double> & energy,
                                  const std::vector<double> & sigma,
                                  double lo, double hi)
{
  if (hi <= lo)
    return 0.0;
  double sum = 0.0;
  while (lo < hi)
  {
    const auto upper = std::upper_bound(energy.begin(), energy.end(), lo);
    std::size_t idx = upper == energy.begin() ? 0 :
                      static_cast<std::size_t>(upper - energy.begin() - 1);
    idx = std::min(idx, energy.size() - 2);
    const double right = std::min(hi, energy[idx + 1]);
    if (!(right > lo))
      throw std::runtime_error("Boltzmann M6: interpolation did not advance");
    const double slope = (sigma[idx + 1] - sigma[idx]) /
                         (energy[idx + 1] - energy[idx]);
    const double sigma_lo = sigma[idx] + slope * (lo - energy[idx]);
    const double dx = right - lo;
    // Integrate (lo+x)*(sigma_lo+slope*x) dx without subtracting close cubes.
    sum += lo * sigma_lo * dx +
           (lo * slope + sigma_lo) * dx * dx / 2.0 +
           slope * dx * dx * dx / 3.0;
    lo = right;
  }
  if (!std::isfinite(sum) || sum < -1e-28)
    throw std::runtime_error("Boltzmann M6: invalid collision cross-section integral");
  return std::max(0.0, sum);
}

void validateInput(const ElasticInput & input,
                   const std::vector<IonizationChannel> & ionizations,
                   const std::vector<AttachmentChannel> & attachments)
{
  if (!std::isfinite(input.max_energy_eV) || !(input.max_energy_eV > 0.0) ||
      input.cells < 2 || input.cells > 16384 || input.targets.empty())
    throw std::invalid_argument("Boltzmann M6: invalid energy grid or gas mixture");
  if (ionizations.empty() && attachments.empty())
    throw std::invalid_argument("Boltzmann M6: at least one growth process is needed");
  std::set<std::string> seen;
  double fraction_sum = 0.0;
  for (const auto & target : input.targets)
  {
    if (target.name.empty() || !seen.insert(target.name).second ||
        !std::isfinite(target.mole_fraction) || !(target.mole_fraction > 0.0))
      throw std::invalid_argument("Boltzmann M6: invalid gas species or fraction");
    fraction_sum += target.mole_fraction;
  }
  if (std::abs(fraction_sum - 1.0) > 1e-12)
    throw std::invalid_argument("Boltzmann M6: mixture fractions must sum to one");
  std::set<std::string> channels;
  for (const auto & c : ionizations)
  {
    validateTable(c.name, c.energy_eV, c.cross_section_m2, input.max_energy_eV);
    if (!(std::isfinite(c.threshold_eV) && c.threshold_eV > 0.0 &&
          c.threshold_eV < input.max_energy_eV) ||
        !channels.insert(c.name).second)
      throw std::invalid_argument("Boltzmann M6: invalid/duplicate ionization channel");
    (void)targetFraction(input, c.target_name);
  }
  for (const auto & c : attachments)
  {
    validateTable(c.name, c.energy_eV, c.cross_section_m2, input.max_energy_eV);
    if (!channels.insert(c.name).second)
      throw std::invalid_argument("Boltzmann M6: duplicate attachment channel");
    (void)targetFraction(input, c.target_name);
  }
}
} // namespace

GrowthOperator assembleGrowthCollisions(
    const ElasticInput & input,
    const std::vector<IonizationChannel> & ionizations,
    const std::vector<AttachmentChannel> & attachments)
{
  validateInput(input, ionizations, attachments);
  const std::size_t n = input.cells;
  const auto edges = energyMeshEdges(input);
  std::vector<std::map<std::size_t, double>> rows(n);
  GrowthOperator op;
  op.energy_cells = n;
  op.ionization_event_columns.assign(n, 0.0);
  op.attachment_event_columns.assign(n, 0.0);
  op.electron_number_mass.resize(n);
  for (std::size_t d = 0; d < n; ++d)
  {
    const double lo = edges[d], hi = edges[d+1];
    op.electron_number_mass[d] = (2.0 / 3.0) *
        (std::pow(hi, 1.5) - std::pow(lo, 1.5));
  }

  for (const auto & channel : ionizations)
  {
    const double x = targetFraction(input, channel.target_name);
    const double u = channel.threshold_eV;
    for (std::size_t donor = 0; donor < n; ++donor)
    {
      const double lo = std::max(edges[donor], u);
      const double hi = edges[donor+1];
      if (hi <= lo)
        continue;
      const double collisions = gamma * x *
          integralEnergyCrossSection(channel.energy_eV, channel.cross_section_m2, lo, hi);
      op.ionization_event_columns[donor] += collisions;
      rows[donor][donor] -= collisions; // one incident electron removed

      // Equal sharing: 2 product electrons with epsilon_out=(epsilon_in-u)/2.
      // Equal sharing maps a donor interval onto arbitrarily many
      // destination cells when their widths are nonuniform.
      const double mapped_lo = (lo-u)/2.0;
      const double mapped_hi = (hi-u)/2.0;
      const std::size_t first = energyMeshCell(edges, mapped_lo);
      const std::size_t last = energyMeshCell(
          edges, std::nextafter(mapped_hi, 0.0));
      double gains = 0.0;
      for (std::size_t dest = first; dest <= last && dest < n; ++dest)
      {
        const double xlo = std::max(lo, u + 2.0 * edges[dest]);
        const double xhi = std::min(hi, u + 2.0 * edges[dest+1]);
        if (xhi <= xlo)
          continue;
        const double contribution = 2.0 * gamma * x *
            integralEnergyCrossSection(channel.energy_eV, channel.cross_section_m2,
                                       xlo, xhi);
        rows[dest][donor] += contribution;
        gains += contribution;
      }
      if (collisions > 0.0 && std::abs(gains - 2.0 * collisions) > 1e-9 * collisions)
        throw std::runtime_error("Boltzmann M6: equal-sharing ionization transfer lost electrons");
    }
  }

  for (const auto & channel : attachments)
  {
    const double x = targetFraction(input, channel.target_name);
    for (std::size_t donor = 0; donor < n; ++donor)
    {
      const double lo = edges[donor], hi = edges[donor+1];
      const double collisions = gamma * x *
          integralEnergyCrossSection(channel.energy_eV, channel.cross_section_m2, lo, hi);
      rows[donor][donor] -= collisions; // electron lost by attachment
      op.attachment_event_columns[donor] += collisions;
    }
  }

  // Independently check assembled column sums, not the bookkeeping sources.
  std::vector<double> assembled_column_sums(n, 0.0);
  for (const auto & row : rows)
    for (const auto & [donor, coefficient] : row)
      assembled_column_sums[donor] += coefficient;
  for (std::size_t donor = 0; donor < n; ++donor)
  {
    const double matrix_sum = assembled_column_sums[donor];
    const double expected = op.ionization_event_columns[donor] -
                            op.attachment_event_columns[donor];
    const double scale = op.ionization_event_columns[donor] +
                         op.attachment_event_columns[donor];
    if (scale > 1e-300)
      op.maximum_number_balance_relative_error = std::max(
          op.maximum_number_balance_relative_error,
          std::abs(matrix_sum - expected) / scale);
  }
  if (op.maximum_number_balance_relative_error > 1e-9)
    throw std::runtime_error("Boltzmann M6: particle-changing operator failed number audit");
  for (std::size_t dest = 0; dest < n; ++dest)
    for (const auto & [donor, value] : rows[dest])
      if (value != 0.0)
        op.entries.push_back({dest, donor, value});
  return op;
}

GrowthDiagnostics evaluateGrowthOnFrozenEepf(
    const ElasticInput & input,
    const ElasticResult & distribution,
    const std::vector<IonizationChannel> & ionizations,
    const std::vector<AttachmentChannel> & attachments)
{
  const auto op = assembleGrowthCollisions(input, ionizations, attachments);
  const std::size_t n = input.cells;
  const auto edges = energyMeshEdges(input);
  const auto centers = energyMeshCenters(edges);
  if (distribution.energy_eV.size() != n ||
      distribution.eepf_eV_minus_3_halves.size() != n)
    throw std::invalid_argument("Boltzmann M6: EEPF size does not match collision grid");
  double norm = 0.0;
  for (std::size_t i = 0; i < n; ++i)
  {
    if (!nonnegative(distribution.eepf_eV_minus_3_halves[i]) ||
        !std::isfinite(distribution.energy_eV[i]) ||
        std::abs(distribution.energy_eV[i] - centers[i]) >
            1e-9 * (edges[i+1]-edges[i]))
      throw std::invalid_argument("Boltzmann M6: EEPF values or energy centers invalid");
    norm += distribution.eepf_eV_minus_3_halves[i] * op.electron_number_mass[i];
  }
  if (std::abs(norm - 1.0) > 1e-8)
    throw std::invalid_argument("Boltzmann M6: EEPF is not normalized");

  GrowthDiagnostics result;
  result.operator_number_balance_relative_error = op.maximum_number_balance_relative_error;
  for (const auto & channel : ionizations)
  {
    double k = 0.0;
    for (std::size_t d = 0; d < n; ++d)
      k += gamma * distribution.eepf_eV_minus_3_halves[d] *
           integralEnergyCrossSection(channel.energy_eV, channel.cross_section_m2,
                                      std::max(edges[d], channel.threshold_eV),
                                      edges[d+1]);
    result.ionization_rates_m3_per_s.push_back(k);
    const double contribution = targetFraction(input, channel.target_name) * k;
    result.reduced_temporal_growth_m3_per_s += contribution;
    result.reduced_ionization_energy_loss_eV_m3_per_s +=
        contribution * channel.threshold_eV;
  }
  for (const auto & channel : attachments)
  {
    double k = 0.0;
    for (std::size_t d = 0; d < n; ++d)
      k += gamma * distribution.eepf_eV_minus_3_halves[d] *
           integralEnergyCrossSection(channel.energy_eV, channel.cross_section_m2,
                                      edges[d], edges[d+1]);
    result.attachment_rates_m3_per_s.push_back(k);
    result.reduced_temporal_growth_m3_per_s -=
        targetFraction(input, channel.target_name) * k;
  }
  double collisional_growth = 0.0;
  for (const auto & e : op.entries)
    collisional_growth += e.coefficient_m3_per_s *
        distribution.eepf_eV_minus_3_halves[e.donor];
  const double denom = std::max(1e-100,
      std::abs(result.reduced_temporal_growth_m3_per_s) +
      std::abs(collisional_growth));
  if (std::abs(collisional_growth - result.reduced_temporal_growth_m3_per_s) >
      1e-9 * denom)
    throw std::runtime_error("Boltzmann M6: growth coefficient does not match operator source");
  return result;
}
} // namespace PhysicsBoltzmann
