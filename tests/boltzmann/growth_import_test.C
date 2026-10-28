#include "PhysicsBoltzmannCrossSections.h"

#include <cmath>
#include <functional>
#include <iostream>
#include <sstream>
#include <stdexcept>

using namespace PhysicsBoltzmann;

namespace
{
void reject(const std::function<void()> & fn)
{
  try { fn(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("Boltzmann M6: missing fail-closed input rejection");
}

std::string fixture()
{
  // User-authored SYNTHETIC values: not experimental Ar/O2 cross sections.
  return
    "SYNTHETIC AR/O2-LABELED M6 INPUT; NOT LXCAT\n"
    "ELASTIC\nAr\n1.37e-5\nSynthetic elastic\n------\n"
    "0.0 5e-20\n2.0 5e-20\n------\n"
    "ELASTIC\nO2\n3.4e-5\nSynthetic elastic\n------\n"
    "0.0 6e-20\n2.0 6e-20\n------\n"
    "EXCITATION\nAr -> Ar_test_exc\n0.25\nSynthetic excitation\n------\n"
    "0.0 0\n0.25 0\n2.0 1e-20\n------\n"
    "IONIZATION\nAr -> Ar_test_plus\n0.65\nSynthetic ionization\n------\n"
    "0.0 0\n0.65 0\n2.0 1e-20\n------\n"
    "ATTACHMENT\nO2 -> O2_test_negative\nSynthetic attachment\n------\n"
    "0.0 0.2e-20\n2.0 0.2e-20\n------\n";
}
} // namespace

int main()
{
  std::istringstream raw(fixture());
  auto records = parseBolsigCrossSections(raw);
  if (!(records.records.size() == 5 &&
        records.records[3].kind == CollisionKind::Ionization &&
        records.records[4].kind == CollisionKind::Attachment &&
        records.records[3].product == "Ar_test_plus" &&
        records.records[4].product == "O2_test_negative"))
    throw std::runtime_error("Boltzmann M6: typed ion/attachment records lost");

  const std::map<std::string, double> fractions = {{"Ar", 0.7}, {"O2", 0.3}};
  reject([&] { (void)prepareElasticExcitation(records, fractions, 2.0); });
  auto imported = prepareGrowthPhysics(records, fractions, 2.0);
  if (!(imported.targets.size() == 2 &&
        imported.excitation_channels.size() == 1 &&
        imported.ionization_channels.size() == 1 &&
        imported.attachment_channels.size() == 1 &&
        imported.ionization_channels[0].threshold_eV == 0.65 &&
        imported.ionization_channels[0].target_name == "Ar" &&
        imported.attachment_channels[0].target_name == "O2"))
    throw std::runtime_error("Boltzmann M6: complete collision mechanism was truncated");

  ElasticInput in;
  in.cells = 125;
  in.max_energy_eV = 2.0;
  in.gas_temperature_K = 3000.0;
  in.reduced_field_Td = 0.1;
  in.targets = imported.targets;
  auto old_solution = solveExcitationSteadyState(in, imported.excitation_channels);
  auto growth = evaluateGrowthOnFrozenEepf(
      in, old_solution.distribution, imported.ionization_channels,
      imported.attachment_channels);
  if (!(growth.ionization_rates_m3_per_s.size() == 1 &&
        growth.attachment_rates_m3_per_s.size() == 1 &&
        growth.ionization_rates_m3_per_s[0] > 0.0 &&
        growth.attachment_rates_m3_per_s[0] > 0.0 &&
        growth.operator_number_balance_relative_error < 1e-9))
    throw std::runtime_error("Boltzmann M6: M5 EEPF to M6 growth integration failed");

  auto wrong = records;
  wrong.records[3].kind = CollisionKind::Effective;
  reject([&] { (void)prepareGrowthPhysics(wrong, fractions, 2.0); });
  wrong = records;
  wrong.records[3].parameter = 3.0;
  reject([&] { (void)prepareGrowthPhysics(wrong, fractions, 2.0); });
  wrong = records;
  wrong.records[4].target = "missing";
  reject([&] { (void)prepareGrowthPhysics(wrong, fractions, 2.0); });
  wrong = records;
  wrong.records[4].energy_eV.back() = 1.0;
  reject([&] { (void)prepareGrowthPhysics(wrong, fractions, 2.0); });

  // S11: a finite Emax must keep, but not activate, true 19.8/24.58 eV
  // threshold-style processes when Emax is 2 eV. Both records and their
  // source locations survive; the 5 original active channels remain.
  const std::string beyond =
      fixture() +
      "EXCITATION\nAr -> beyond-grid\n19.8\nsynthetic\n------\n"
      "19.8 0\n25 5e-20\n------\n"
      "IONIZATION\nAr -> beyond-grid-plus\n24.58\nsynthetic\n------\n"
      "24.58 0\n30 5e-20\n------\n";
  std::istringstream beyond_stream(beyond);
  const auto complete = parseBolsigCrossSections(beyond_stream);
  reject([&] { (void)prepareGrowthPhysics(complete, fractions, 2.0); });
  const auto selected = normalizeBolsig2024CollisionFile(complete, 2.0, true);
  const auto restricted = prepareGrowthPhysics(selected, fractions, 2.0, false, true);
  if (!(complete.records.size() == 7 &&
        selected.records.size() == 7 &&
        restricted.inactive_above_energy_ceiling.size() == 2 &&
        restricted.inactive_above_energy_ceiling[0].kind == CollisionKind::Excitation &&
        restricted.inactive_above_energy_ceiling[1].kind == CollisionKind::Ionization &&
        restricted.inactive_above_energy_ceiling[0].threshold_eV == 19.8 &&
        restricted.inactive_above_energy_ceiling[1].threshold_eV == 24.58 &&
        restricted.excitation_channels.size() == 1 &&
        restricted.ionization_channels.size() == 1 &&
        restricted.attachment_channels.size() == 1))
    throw std::runtime_error("BOLSIG S11 zero-rate inactive channel audit failed");
  std::cout << "BOLTZMANN_S11_INACTIVE_HIGH_THRESHOLD_P0_P1_PASS\n";
  std::cout << "BOLTZMANN_GROWTH_M6_IMPORT_P0_P1_PASS\n"
            << "M6_IMPORTED_ION_RATE=" << growth.ionization_rates_m3_per_s[0]
            << "\nM6_IMPORTED_ATTACHMENT_RATE=" << growth.attachment_rates_m3_per_s[0]
            << "\n";
}
