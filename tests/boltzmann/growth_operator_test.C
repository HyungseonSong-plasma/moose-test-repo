#include "PhysicsBoltzmannGrowth.h"

#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>

using namespace PhysicsBoltzmann;

namespace
{
void reject(const std::function<void()> & action)
{
  try { action(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("Boltzmann M6: expected malformed-input rejection");
}

ElasticInput fixture(std::size_t cells)
{
  ElasticInput in;
  in.cells = cells;
  in.max_energy_eV = 2.0;
  in.reduced_field_Td = 0.1;
  in.gas_temperature_K = 3000.0;
  in.targets = {{"Ar", 0.7, 1.37e-5, {0.0, 2.0}, {5e-20, 5e-20}},
                {"O2", 0.3, 3.4e-5, {0.0, 2.0}, {6e-20, 6e-20}}};
  return in;
}

IonizationChannel ion()
{
  return {"synthetic_ionization", "Ar", 0.25, {0.0, 2.0}, {1e-20, 1e-20}};
}

AttachmentChannel attachment()
{
  return {"synthetic_attachment", "O2", {0.0, 2.0}, {0.2e-20, 0.2e-20}};
}

void physicsAudit(std::size_t cells)
{
  const auto in = fixture(cells);
  const auto f = solveElasticSteadyState(in);
  const auto ion_channel = ion();
  const auto att_channel = attachment();
  const auto op = assembleGrowthCollisions(in, {ion_channel}, {att_channel});
  const auto coeff = evaluateGrowthOnFrozenEepf(in, f, {ion_channel}, {att_channel});

  if (!(op.energy_cells == cells && op.entries.size() < 5 * cells &&
        op.maximum_number_balance_relative_error < 1e-12 &&
        coeff.operator_number_balance_relative_error < 1e-12))
    throw std::runtime_error("Boltzmann M6: sparse operator or global number audit failed");

  const double h = in.max_energy_eV / cells;
  const double gamma = std::sqrt(2.0 * 1.602176634e-19 / 9.1093837139e-31);
  double independent_ion = 0.0, independent_att = 0.0;
  const auto & eepf = f.eepf_eV_minus_3_halves;
  for (std::size_t i = 0; i < cells; ++i)
  {
    const double a = i * h, b = (i + 1) * h;
    const double a_ion = std::max(a, ion_channel.threshold_eV);
    if (b > a_ion)
      independent_ion += eepf[i] * gamma * 1e-20 *
                         (b * b - a_ion * a_ion) / 2.0;
    independent_att += eepf[i] * gamma * 0.2e-20 *
                       (b * b - a * a) / 2.0;

    // Each ionization contributes exactly +1 electron; each attachment -1.
    const double expected = op.ionization_event_columns[i] -
                            op.attachment_event_columns[i];
    double colsum = 0.0;
    for (const auto & entry : op.entries)
      if (entry.donor == i)
        colsum += entry.coefficient_m3_per_s;
    const double scale = op.ionization_event_columns[i] +
                         op.attachment_event_columns[i];
    if (scale > 0.0 && std::abs(colsum - expected) > 1e-11 * scale)
      throw std::runtime_error("Boltzmann M6: nonconservative column ledger");
  }

  if (std::abs(independent_ion - coeff.ionization_rates_m3_per_s.at(0)) >
          1e-11 * independent_ion ||
      std::abs(independent_att - coeff.attachment_rates_m3_per_s.at(0)) >
          1e-11 * independent_att)
    throw std::runtime_error("Boltzmann M6: per-target rate oracle mismatch");

  const double expected_growth = 0.7 * independent_ion - 0.3 * independent_att;
  const double expected_energy_loss = 0.7 * ion_channel.threshold_eV * independent_ion;
  if (std::abs(expected_growth - coeff.reduced_temporal_growth_m3_per_s) >
          1e-11 * (0.7 * independent_ion + 0.3 * independent_att) ||
      std::abs(expected_energy_loss - coeff.reduced_ionization_energy_loss_eV_m3_per_s) >
          1e-11 * expected_energy_loss)
    throw std::runtime_error("Boltzmann M6: growth/ionization energy moment mismatch");

  // An ionization event lowers total electron kinetic energy by its threshold.
  // Piecewise-constant f0 and cell-centered deposited energy lead to O(h)
  // discrepancy. No such claim is made for threshold ionization+attachment.
  const auto ion_only = assembleGrowthCollisions(in, {ion_channel}, {});
  for (std::size_t i = 0; i < cells; ++i)
  {
    const double events = ion_only.ionization_event_columns[i];
    if (!(events > 0.0))
      continue;
    double energy_change = 0.0;
    for (const auto & entry : ion_only.entries)
      if (entry.donor == i)
        energy_change += entry.coefficient_m3_per_s *
            ((entry.destination + 0.5) * h);
    // M6 equal-sharing yields two children at (epsilon-u)/2.
    const double defect = energy_change + ion_channel.threshold_eV * events;
    if (std::abs(defect) > 3.0 * h * events)
      throw std::runtime_error("Boltzmann M6: event kinetic-energy budget failed");
  }
}
} // namespace

int main()
{
  physicsAudit(100);
  physicsAudit(250);
  physicsAudit(800); // large sparse operator, no dense collision matrix

  const auto in = fixture(100);
  const auto f = solveElasticSteadyState(in);
  const auto growth_ion = evaluateGrowthOnFrozenEepf(in, f, {ion()}, {});
  const auto growth_att = evaluateGrowthOnFrozenEepf(in, f, {}, {attachment()});
  if (!(growth_ion.reduced_temporal_growth_m3_per_s > 0.0 &&
        growth_att.reduced_temporal_growth_m3_per_s < 0.0))
    throw std::runtime_error("Boltzmann M6: particle sign convention invalid");

  auto bad_ion = ion();
  bad_ion.threshold_eV = 2.0;
  reject([&] { (void)assembleGrowthCollisions(in, {bad_ion}, {}); });
  bad_ion = ion();
  bad_ion.target_name = "missing";
  reject([&] { (void)assembleGrowthCollisions(in, {bad_ion}, {}); });
  bad_ion = ion();
  bad_ion.cross_section_m2[0] = -1.0;
  reject([&] { (void)assembleGrowthCollisions(in, {bad_ion}, {}); });
  bad_ion = ion();
  bad_ion.energy_eV[1] = 0.0;
  reject([&] { (void)assembleGrowthCollisions(in, {bad_ion}, {}); });
  bad_ion = ion();
  bad_ion.energy_eV.back() = 1.0;
  reject([&] { (void)assembleGrowthCollisions(in, {bad_ion}, {}); });
  auto bad_att = attachment();
  bad_att.name = ion().name;
  reject([&] { (void)assembleGrowthCollisions(in, {ion()}, {bad_att}); });
  reject([&] { (void)assembleGrowthCollisions(in, {}, {}); });

  auto broken = f;
  broken.eepf_eV_minus_3_halves[0] *= 2.0;
  reject([&] { (void)evaluateGrowthOnFrozenEepf(in, broken, {ion()}, {}); });

  std::cout << "BOLTZMANN_GROWTH_M6A_P0_P1_PASS\n"
            << "M6_IONIZATION_REDUCED_GROWTH=" << growth_ion.reduced_temporal_growth_m3_per_s
            << "\nM6_ATTACHMENT_REDUCED_GROWTH=" << growth_att.reduced_temporal_growth_m3_per_s
            << "\n";
}
