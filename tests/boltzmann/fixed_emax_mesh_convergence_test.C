// P0-2: actual C++ M6b fixed-Emax refinement; FIRST-PARTY SYNTHETIC ONLY.
// Not native BOLSIG+/LXCat parity, not a production accuracy claim.
#include "PhysicsBoltzmannMeshRefinement.h"

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
void rejects(const std::function<void()> & fn)
{
  try { fn(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("P0-2 fixed Emax: invalid input was accepted");
}
ElasticInput fixture()
{
  ElasticInput in;
  in.reduced_field_Td = 0.05;
  in.gas_temperature_K = 1000.0;
  in.max_energy_eV = 4.0;
  in.cells = 16;
  in.targets = {{"synthetic-neutral", 1.0, 1.37e-5,
                 {0.0, 16.0}, {5e-20, 5e-20}}};
  return in;
}
} // namespace

int main()
{
  // Manufactured normalized EEPFs: conservative L1 must be independent of
  // the two grids, symmetric, and sensitive to a genuine shape change.
  const double total_mass = (2.0 / 3.0) * std::pow(2.0, 1.5);
  const double f0 = 1.0 / total_mass;
  ElasticResult a, b;
  a.energy_cell_edges_eV = {0.0, 2.0};
  a.eepf_eV_minus_3_halves = {f0};
  b.energy_cell_edges_eV = {0.0, 1.0, 2.0};
  b.eepf_eV_minus_3_halves = {f0, f0};
  require(fvEepfL1Distance(a, b) < 1e-13 &&
          fvEepfL1Distance(b, a) < 1e-13,
          "P0-2 fixed Emax: identical distribution changed across grids");
  const double left_mass = 2.0 / 3.0;
  b.eepf_eV_minus_3_halves[0] = 1.2 * f0;
  b.eepf_eV_minus_3_halves[1] =
      (1.0 - left_mass * b.eepf_eV_minus_3_halves[0]) /
      (total_mass - left_mass);
  const double l1 = fvEepfL1Distance(a, b);
  require(l1 > 0.1 && l1 < 0.2 &&
          std::abs(l1 - fvEepfL1Distance(b, a)) < 1e-13,
          "P0-2 fixed Emax: conservative L1 shape change not detected");
  rejects([&] {
    auto bad = b;
    bad.eepf_eV_minus_3_halves[0] *= 2.0;
    (void)fvEepfL1Distance(a, bad);
  });
  rejects([&] {
    auto bad = b;
    bad.energy_cell_edges_eV.back() = 3.0;
    (void)fvEepfL1Distance(a, bad);
  });

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

  MeshRefinementControls c;
  c.initial_base_cells = 16;
  c.maximum_base_cells = 120;
  c.maximum_refinements = 4;
  c.required_stable_refinements = 2;
  // Deliberately permissive to test convergence state transitions;
  // these are NOT science-accepted physical error tolerances.
  c.mean_relative_limit = 1.0;
  c.rate_relative_limit = 1.0;
  c.distribution_l1_limit = 2.0;
  const auto selected = solveTemporalGrowthWithMeshRefinement(
      initial, ions, attaches, excitations, c);
  require(selected.converged &&
          selected.status == "CONVERGED_FIXED_EMAX_MESH_SCIENCE_HOLD" &&
          selected.history.size() == 3,
          "P0-2 fixed Emax: monitored mesh convergence did not finish");
  std::size_t previous_base = 0, previous_actual = 0;
  for (const auto & step : selected.history)
  {
    require(step.base_cells > previous_base &&
            step.actual_cells > previous_actual &&
            step.eigen_residual < 1e-8 &&
            step.collision_number_balance_error < 1e-9 &&
            step.mean_energy_eV > 0.0,
            "P0-2 fixed Emax: invalid coupled solve or refinement");
    previous_base = step.base_cells;
    previous_actual = step.actual_cells;
  }
  const auto & last = selected.history.back();
  require(last.stable && std::isfinite(last.mean_relative_change) &&
          std::isfinite(last.maximum_rate_relative_change) &&
          std::isfinite(last.distribution_l1_change) &&
          last.distribution_l1_change <= 2.0,
          "P0-2 fixed Emax: missing monitored convergence diagnostics");
  require(selected.distribution.energy_cell_edges_eV.back() ==
          initial.max_energy_eV,
          "P0-2 fixed Emax: ceiling changed during mesh refinement");

  // Tight tolerances must fail closed rather than re-label an unfinished
  // mesh study as scientific convergence.
  auto strict = c;
  strict.mean_relative_limit = 1e-14;
  strict.rate_relative_limit = 1e-14;
  strict.distribution_l1_limit = 1e-14;
  strict.maximum_refinements = 2;
  const auto not_converged = solveTemporalGrowthWithMeshRefinement(
      initial, ions, attaches, excitations, strict);
  require(!not_converged.converged &&
          not_converged.status == "HOLD_MAX_REFINEMENTS" &&
          not_converged.history.size() == 3,
          "P0-2 fixed Emax: strict tolerance incorrectly passed");

  auto budget = strict;
  budget.maximum_refinements = 4;
  budget.mesh.maximum_cells = 16;
  const auto capped = solveTemporalGrowthWithMeshRefinement(
      initial, ions, attaches, excitations, budget);
  require(!capped.converged &&
          capped.status == "HOLD_DENSE_REFERENCE_CELL_LIMIT" &&
          capped.history.empty(),
          "P0-2 fixed Emax: dense cell limit failed open");
  rejects([&] {
    auto invalid = c;
    invalid.base_growth_factor = 1.0;
    (void)solveTemporalGrowthWithMeshRefinement(
        initial, ions, attaches, excitations, invalid);
  });

  std::cout << "P0-2 fixed Emax synthetic actual M6b: Emax="
            << initial.max_energy_eV << " eV, base_cells="
            << last.base_cells << ", FV_cells=" << last.actual_cells
            << ", mean=" << last.mean_energy_eV
            << " eV, mean_relative_change=" << last.mean_relative_change
            << ", max_rate_relative_change="
            << last.maximum_rate_relative_change
            << ", EEPF_L1=" << last.distribution_l1_change
            << ", eigen_residual=" << last.eigen_residual
            << ", number_balance=" << last.collision_number_balance_error
            << ", strict_HOLD=PASS, dense_HOLD=PASS; NOT BOLSIG+ PARITY\n";
}
