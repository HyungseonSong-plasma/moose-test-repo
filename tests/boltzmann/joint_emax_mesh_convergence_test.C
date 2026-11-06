// P0-1/P0-2 joint gate: actual compiled C++ M6b re-solves.
// All collision tables below are FIRST-PARTY SYNTHETIC, NOT LXCat/BOLSIG+.
#include "PhysicsBoltzmannJointConvergence.h"

#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace PhysicsBoltzmann;

namespace
{
void require(bool ok, const std::string & reason)
{
  if (!ok)
    throw std::runtime_error(reason);
}
void rejects(const std::function<void()> & fn)
{
  try { fn(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("P0 joint gate: invalid input accepted");
}
ElasticInput fixture()
{
  ElasticInput in;
  in.reduced_field_Td = 0.05;
  in.gas_temperature_K = 1000.0;
  in.max_energy_eV = 2.0;
  in.cells = 12;
  in.targets = {{"synthetic-neutral", 1.0, 1.37e-5,
                 {0.0, 16.0}, {5e-20, 5e-20}}};
  return in;
}
JointGrowthControls controls()
{
  JointGrowthControls c;
  c.ceiling.maximum_energy_eV = 12.0;
  c.ceiling.expansion_factor = 1.5;
  c.ceiling.max_expansions = 6;
  c.ceiling.required_stable_expansions = 2;
  c.ceiling.tail_mass_limit = 1e-2;
  c.ceiling.tail_energy_limit = 1e-2;
  c.ceiling.moment_relative_limit = 1.0;
  c.ceiling.rate_relative_limit = 1.0;
  c.refinement.initial_base_cells = 12;
  c.refinement.maximum_base_cells = 120;
  c.refinement.maximum_refinements = 2;
  c.refinement.required_stable_refinements = 1;
  c.refinement.base_growth_factor = 1.3;
  // Intentionally permissive to test the *joint gate state machine*.
  // These are NOT scientifically defensible convergence tolerances.
  c.refinement.mean_relative_limit = 1.0;
  c.refinement.rate_relative_limit = 1.0;
  c.refinement.distribution_l1_limit = 2.0;
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
  const auto joint = solveTemporalGrowthWithJointConvergence(
      initial, ions, attaches, excitations, c);
  require(joint.ceiling.converged &&
          joint.ceiling.status == "CONVERGED_JOINT_EMAX_MESH_SCIENCE_HOLD" &&
          joint.trials.size() == joint.ceiling.history.size() &&
          joint.trials.size() >= 3,
          "P0 joint gate: permissive nested convergence did not complete");
  for (std::size_t i = 0; i < joint.trials.size(); ++i)
  {
    const auto & t = joint.trials[i];
    const auto & step = joint.ceiling.history[i];
    require(t.mesh_converged &&
            t.mesh_status == "CONVERGED_FIXED_EMAX_MESH_SCIENCE_HOLD" &&
            t.mesh_history.size() == 2 &&
            t.mesh_history.back().stable &&
            t.mesh_history.back().actual_cells >
                t.mesh_history.front().actual_cells &&
            step.energy_ceiling_eV == t.energy_ceiling_eV &&
            step.cells == t.mesh_history.back().actual_cells &&
            step.rates_monitored && step.thresholds_monitored &&
            step.threshold_resolved &&
            t.mesh_history.back().eigen_residual < 1e-8 &&
            t.mesh_history.back().collision_number_balance_error < 1e-9,
            "P0 joint gate: an Emax trial bypassed the inner mesh/eigen/rate gate");
  }
  const auto & last = joint.ceiling.history.back();
  const auto & distribution = joint.ceiling.distribution;
  require(last.stable && last.tail_number_fraction <= c.ceiling.tail_mass_limit &&
          last.tail_energy_fraction <= c.ceiling.tail_energy_limit &&
          last.maximum_rate_relative_change <= c.ceiling.rate_relative_limit &&
          distribution.energy_cell_edges_eV.back() == last.energy_ceiling_eV,
          "P0 joint gate: final Emax not evaluated on refined mesh");

  // Tight inner tolerances must stop the OUTER ceiling immediately. They
  // cannot be bypassed by an otherwise tiny EEPF tail or stable rates.
  auto strict = c;
  strict.refinement.mean_relative_limit = 1e-14;
  strict.refinement.rate_relative_limit = 1e-14;
  strict.refinement.distribution_l1_limit = 1e-14;
  strict.refinement.maximum_refinements = 1;
  const auto held = solveTemporalGrowthWithJointConvergence(
      initial, ions, attaches, excitations, strict);
  require(!held.ceiling.converged &&
          held.ceiling.status == "HOLD_JOINT_MESH_HOLD_MAX_REFINEMENTS" &&
          held.ceiling.history.empty() &&
          held.trials.size() == 1 &&
          !held.trials.front().mesh_converged &&
          held.trials.front().mesh_history.size() == 2,
          "P0 joint gate: unresolved mesh falsely approved Emax");

  // Dense cell budget must fail closed before any accepted ceiling sample.
  auto budget = c;
  budget.refinement.mesh.maximum_cells = 12;
  const auto capped = solveTemporalGrowthWithJointConvergence(
      initial, ions, attaches, excitations, budget);
  require(!capped.ceiling.converged &&
          capped.ceiling.status == "HOLD_JOINT_MESH_HOLD_DENSE_REFERENCE_CELL_LIMIT" &&
          capped.ceiling.history.empty() && capped.trials.size() == 1 &&
          capped.trials.front().mesh_history.empty(),
          "P0 joint gate: dense cell resource limit failed open");

  rejects([&] {
    auto truncated = ions;
    truncated.front().energy_eV.back() = 8.0;
    (void)solveTemporalGrowthWithJointConvergence(
        initial, truncated, attaches, excitations, c);
  });
  rejects([&] {
    auto dormant = ions;
    dormant.front().threshold_eV = initial.max_energy_eV;
    (void)solveTemporalGrowthWithJointConvergence(
        initial, dormant, attaches, excitations, c);
  });
  rejects([&] {
    (void)solveTemporalGrowthWithJointConvergence(
        initial, {}, {}, excitations, c);
  });
  rejects([&] {
    auto bad = c;
    bad.refinement.mesh.maximum_cells = 300;
    (void)solveTemporalGrowthWithJointConvergence(
        initial, ions, attaches, excitations, bad);
  });

  std::cout << "P0 joint actual synthetic M6b: Emax="
            << last.energy_ceiling_eV << " eV, refined_cells="
            << last.cells << ", mean=" << last.mean_energy_eV
            << " eV, max_rate_change=" << last.maximum_rate_relative_change
            << ", final_mesh_L1="
            << joint.trials.back().mesh_history.back().distribution_l1_change
            << ", final_eigen_residual="
            << joint.trials.back().mesh_history.back().eigen_residual
            << ", mesh_strict_HOLD=PASS, dense_HOLD=PASS"
            << "; NOT BOLSIG+ PARITY\\n";
}
