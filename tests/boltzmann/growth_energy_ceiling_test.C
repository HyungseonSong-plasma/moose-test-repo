// First-party synthetic collision data; no LXCat/BOLSIG+ rows or native parity.
// Exercises actual C++ M6b temporal-growth eigen re-solves, not frozen EEPFs.
#include "PhysicsBoltzmannGrowthCeiling.h"

#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace PhysicsBoltzmann;

namespace
{
void require(bool condition, const std::string & message)
{
  if (!condition)
    throw std::runtime_error(message);
}

void rejects(const std::function<void()> & call)
{
  try { call(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("P0-1 growth Emax: invalid input was accepted");
}

ElasticInput fixture(std::size_t cells = 24)
{
  ElasticInput input;
  input.reduced_field_Td = 0.05;
  input.gas_temperature_K = 1000.0;
  input.max_energy_eV = 2.0;
  input.cells = cells;
  input.targets = {{"synthetic-neutral", 1.0, 1.37e-5,
                    {0.0, 16.0}, {5e-20, 5e-20}}};
  return input;
}

IonizationChannel ionization()
{
  return {"synthetic-ion", "synthetic-neutral", 0.5,
          {0.0, 0.5, 16.0}, {0.0, 0.0, 1e-25}};
}

AttachmentChannel attachment()
{
  return {"synthetic-attachment", "synthetic-neutral",
          {0.0, 16.0}, {1e-26, 1e-26}};
}

ExcitationChannel excitation()
{
  return {"synthetic-excitation", "synthetic-neutral", 0.8,
          {0.0, 0.8, 16.0}, {0.0, 0.0, 1e-25}};
}

EnergyCeilingControls controls()
{
  EnergyCeilingControls c;
  c.maximum_energy_eV = 12.0;
  c.expansion_factor = 1.5;
  c.max_expansions = 7;
  c.required_stable_expansions = 2;
  c.tail_mass_limit = 1e-5;
  c.tail_energy_limit = 1e-4;
  c.moment_relative_limit = 1e-2;
  c.rate_relative_limit = 1e-2;
  return c;
}
} // namespace

int main()
{
  const auto input = fixture();
  const auto ions = std::vector<IonizationChannel>{ionization()};
  const auto attaches = std::vector<AttachmentChannel>{attachment()};
  const auto excitations = std::vector<ExcitationChannel>{excitation()};
  const auto c = controls();

  // Ionization, attachment and excitation are all active and are rebuilt
  // for every independent ceiling. Rates are obtained from the new eigen-EEPF.
  const auto selected = solveTemporalGrowthWithAutomaticCeiling(
      input, ions, attaches, excitations, c);
  require(selected.converged && selected.history.size() >= 3 &&
          selected.status == "CONVERGED_MONITORED_RATES_SCIENCE_HOLD",
          "P0-1 growth: coupled eigen/rate ceiling did not converge");
  for (const auto & step : selected.history)
    require(step.rates_monitored && step.thresholds_monitored &&
            step.cells >= input.cells,
            "P0-1 growth: rates/thresholds not audited on every eigen solve");
  const auto & last = selected.history.back();
  require(last.cells > input.cells && last.stable &&
          last.threshold_resolved &&
          last.tail_number_fraction <= c.tail_mass_limit &&
          last.tail_energy_fraction <= c.tail_energy_limit &&
          last.maximum_rate_relative_change <= c.rate_relative_limit,
          "P0-1 growth: selected ceiling violates monitored invariant");

  ElasticInput final_input = input;
  final_input.max_energy_eV = last.energy_ceiling_eV;
  final_input.cells = last.cells;
  const auto independently_recomputed = solveElasticTemporalGrowth(
      final_input, ions, attaches, excitations);
  require(independently_recomputed.maximum_normalized_eigen_residual < 1e-8 &&
          std::abs(independently_recomputed.distribution.mean_energy_eV -
                   selected.distribution.mean_energy_eV) < 1e-9,
          "P0-1 growth: selected EEPF differs from independent final eigen solve");
  const auto final_rates = evaluateGrowthOnFrozenEepf(
      final_input, selected.distribution, ions, attaches);
  require(final_rates.ionization_rates_m3_per_s.size() == 1 &&
          final_rates.attachment_rates_m3_per_s.size() == 1 &&
          final_rates.operator_number_balance_relative_error < 1e-9 &&
          final_rates.ionization_rates_m3_per_s[0] > 0.0 &&
          final_rates.attachment_rates_m3_per_s[0] > 0.0,
          "P0-1 growth: actual ionization/attachment rate audit failed");
  const auto excitation_rates = evaluateExcitationRatesOnEepf(
      final_input, selected.distribution, excitations);
  require(excitation_rates.forward_rates_m3_per_s.size() == 1 &&
          excitation_rates.forward_rates_m3_per_s[0] > 0.0,
          "P0-1 growth: actual excitation rate was not evaluated");

  // A 256-cell initial dense reference cannot expand without violating its
  // hard numerical budget. It must HOLD, not declare a one-sample PASS.
  const auto budget = solveTemporalGrowthWithAutomaticCeiling(
      fixture(256), ions, attaches, {}, c);
  require(!budget.converged &&
          budget.status == "HOLD_DENSE_REFERENCE_CELL_LIMIT" &&
          budget.history.size() == 1,
          "P0-1 growth: dense eigensolver cell budget was silently bypassed");

  rejects([&] {
    auto bad = input;
    bad.energy_cell_edges_eV.resize(bad.cells + 1);
    (void)solveTemporalGrowthWithAutomaticCeiling(
        bad, ions, attaches, excitations, c);
  });
  rejects([&] {
    auto truncated = ions;
    truncated[0].energy_eV.back() = 8.0;
    (void)solveTemporalGrowthWithAutomaticCeiling(
        input, truncated, attaches, excitations, c);
  });
  rejects([&] {
    auto dormant = ions;
    dormant[0].threshold_eV = input.max_energy_eV;
    (void)solveTemporalGrowthWithAutomaticCeiling(
        input, dormant, attaches, excitations, c);
  });
  rejects([&] {
    (void)solveTemporalGrowthWithAutomaticCeiling(
        input, {}, {}, excitations, c);
  });

  std::cout << "P0-1 actual synthetic M6b coupled ion/attachment/excitation"
            << " Emax=" << last.energy_ceiling_eV
            << " eV, cells=" << last.cells
            << ", mean=" << last.mean_energy_eV
            << " eV, max_rate_change=" << last.maximum_rate_relative_change
            << ", eigen_residual="
            << independently_recomputed.maximum_normalized_eigen_residual
            << "; dense budget HOLD verified; NOT BOLSIG+ PARITY\\n";
}
