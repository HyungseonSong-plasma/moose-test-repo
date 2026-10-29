// P0-1/P0-2 integration test: FIRST-PARTY SYNTHETIC cross sections only.
// This is an actual compiled C++ coupled M6b eigen/rate re-solve on every
// independently selected Emax and freshly constructed nonuniform FV mesh.
// It is NOT an LXCat/BOLSIG+ Example 1-4 native-parity test.
#include "PhysicsBoltzmannAdaptiveGrowth.h"

#include <algorithm>
#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace PhysicsBoltzmann;

namespace
{
void require(bool ok, const std::string & message)
{
  if (!ok)
    throw std::runtime_error(message);
}
void rejects(const std::function<void()> & run)
{
  try { run(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("P0 adaptive growth: invalid input accepted");
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
  const auto initial = fixture();
  const std::vector<IonizationChannel> ions = {
      {"synthetic-ion", "synthetic-neutral", 0.5,
       {0.0, 0.5, 16.0}, {0.0, 0.0, 1e-25}}};
  const std::vector<AttachmentChannel> attaches = {
      {"synthetic-attachment", "synthetic-neutral",
       {0.0, 16.0}, {1e-26, 1e-26}}};
  const std::vector<ExcitationChannel> excitations = {
      {"synthetic-excitation", "synthetic-neutral", 0.8,
       {0.0, 0.8, 16.0}, {0.0, 0.0, 1e-25}}};
  const auto c = controls();
  ThresholdMeshControls mesh;
  mesh.maximum_cells = 256;
  const auto result = solveTemporalGrowthWithAdaptiveMesh(
      initial, ions, attaches, excitations, c, mesh);
  require(result.converged && result.history.size() >= 3 &&
          result.status == "CONVERGED_MONITORED_RATES_SCIENCE_HOLD",
          "P0 adaptive growth: no monitored Emax convergence");

  // Every Emax trial must use a new, threshold-aligned nonuniform grid,
  // preserving nominal low-energy resolution as the ceiling expands.
  for (const auto & step : result.history)
  {
    const auto base = static_cast<std::size_t>(std::ceil(
        static_cast<double>(initial.cells) * step.energy_ceiling_eV /
        initial.max_energy_eV));
    const auto expected = buildThresholdAwareMesh(
        step.energy_ceiling_eV, base, {0.5, 0.8}, mesh);
    require(step.cells == expected.edges_eV.size() - 1 &&
            step.cells > base && step.rates_monitored &&
            step.thresholds_monitored && step.threshold_resolved,
            "P0 adaptive growth: a trial did not rebuild threshold mesh/rates");
  }
  const auto & last = result.history.back();
  require(last.stable && last.tail_number_fraction <= c.tail_mass_limit &&
          last.tail_energy_fraction <= c.tail_energy_limit &&
          last.maximum_rate_relative_change <= c.rate_relative_limit &&
          last.mean_relative_change <= c.moment_relative_limit,
          "P0 adaptive growth: selected ceiling violates convergence limits");

  const auto base = static_cast<std::size_t>(std::ceil(
      static_cast<double>(initial.cells) * last.energy_ceiling_eV /
      initial.max_energy_eV));
  ElasticInput independent_input = initial;
  independent_input.max_energy_eV = last.energy_ceiling_eV;
  independent_input.cells = base;
  independent_input = withThresholdAwareMesh(
      independent_input, {0.5, 0.8}, mesh);
  require(result.distribution.energy_cell_edges_eV ==
          independent_input.energy_cell_edges_eV,
          "P0 adaptive growth: final FV mesh differs from independent rebuild");
  const auto independent = solveElasticTemporalGrowth(
      independent_input, ions, attaches, excitations);
  require(independent.maximum_normalized_eigen_residual < 1e-8 &&
          std::abs(independent.distribution.mean_energy_eV -
                   result.distribution.mean_energy_eV) < 1e-9,
          "P0 adaptive growth: final result differs from independent eigen solve");

  const auto & edges = result.distribution.energy_cell_edges_eV;
  const auto & f = result.distribution.eepf_eV_minus_3_halves;
  double mass = 0.0;
  for (std::size_t i = 0; i < f.size(); ++i)
  {
    require(std::isfinite(f[i]) && f[i] >= 0.0,
            "P0 adaptive growth: nonphysical EEPF");
    mass += f[i] * (2.0 / 3.0) *
        (std::pow(edges[i + 1], 1.5) - std::pow(edges[i], 1.5));
  }
  require(std::abs(mass - 1.0) < 1e-8,
          "P0 adaptive growth: FV mass normalization lost");
  const auto growth = evaluateGrowthOnFrozenEepf(
      independent_input, result.distribution, ions, attaches);
  require(growth.operator_number_balance_relative_error < 1e-9 &&
          growth.ionization_rates_m3_per_s.size() == 1 &&
          growth.attachment_rates_m3_per_s.size() == 1 &&
          growth.ionization_rates_m3_per_s[0] > 0.0 &&
          growth.attachment_rates_m3_per_s[0] > 0.0,
          "P0 adaptive growth: source/gain conservation or rates failed");
  const auto excitation_rates = evaluateExcitationRatesOnEepf(
      independent_input, result.distribution, excitations);
  require(excitation_rates.forward_rates_m3_per_s.size() == 1 &&
          excitation_rates.forward_rates_m3_per_s[0] > 0.0,
          "P0 adaptive growth: excitation rate was not recomputed");

  // A tight cell budget must return an explicit HOLD and retain any
  // successful earlier Emax samples; it must not coarsen to force PASS.
  auto capped_mesh = mesh;
  capped_mesh.maximum_cells = 100;
  const auto capped = solveTemporalGrowthWithAdaptiveMesh(
      initial, ions, attaches, excitations, c, capped_mesh);
  require(!capped.converged &&
          capped.status == "HOLD_DENSE_REFERENCE_CELL_LIMIT" &&
          !capped.history.empty() &&
          capped.distribution.energy_cell_edges_eV.size() > 2,
          "P0 adaptive growth: resource HOLD lost prior numerical evidence");
  const auto impossible = solveTemporalGrowthWithAdaptiveMesh(
      fixture(245), ions, attaches, excitations, c, mesh);
  require(!impossible.converged &&
          impossible.status == "HOLD_DENSE_REFERENCE_CELL_LIMIT" &&
          impossible.history.empty(),
          "P0 adaptive growth: oversized first grid failed open");

  rejects([&] {
    auto bad = initial;
    bad.energy_cell_edges_eV.resize(bad.cells + 1);
    (void)solveTemporalGrowthWithAdaptiveMesh(
        bad, ions, attaches, excitations, c, mesh);
  });
  rejects([&] {
    auto truncated = ions;
    truncated[0].energy_eV.back() = 8.0;
    (void)solveTemporalGrowthWithAdaptiveMesh(
        initial, truncated, attaches, excitations, c, mesh);
  });
  rejects([&] {
    auto dormant = ions;
    dormant[0].threshold_eV = initial.max_energy_eV;
    (void)solveTemporalGrowthWithAdaptiveMesh(
        initial, dormant, attaches, excitations, c, mesh);
  });
  rejects([&] {
    (void)solveTemporalGrowthWithAdaptiveMesh(
        initial, {}, {}, excitations, c, mesh);
  });
  rejects([&] {
    auto oversized = mesh;
    oversized.maximum_cells = 300;
    (void)solveTemporalGrowthWithAdaptiveMesh(
        initial, ions, attaches, excitations, c, oversized);
  });

  std::cout << "P0-1/P0-2 actual synthetic adaptive M6b Emax="
            << last.energy_ceiling_eV << " eV, cells=" << last.cells
            << ", mean=" << last.mean_energy_eV
            << " eV, eigen_residual="
            << independent.maximum_normalized_eigen_residual
            << ", FV_mass=" << mass
            << ", source_balance="
            << growth.operator_number_balance_relative_error
            << ", max_rate_change=" << last.maximum_rate_relative_change
            << ", resource_HOLD_with_history=PASS; NOT BOLSIG+ PARITY\n";
}
