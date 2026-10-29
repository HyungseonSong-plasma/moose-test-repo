// First-party SYNTHETIC process tables. P0-3 growth-only reconstruction;
// NOT actual Ar/LXCat data, NOT BOLSIG+ rate/EEPF parity.
#include "PhysicsBoltzmannReconstructedGrowth.h"
#include "PhysicsBoltzmannSubcellReconstruction.h"

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
void require(bool ok, const std::string & reason)
{
  if (!ok)
    throw std::runtime_error(reason);
}
void rejects(const std::function<void()> & fn)
{
  try { fn(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("P0-3: invalid reconstruction input accepted");
}
}

int main()
{
  // Deliberately manufactured steep tail and the C3 *energy window*.
  // The actual C3 cross section/EEPF are not used or claimed.
  const std::vector<double> edges = {0.0, 1.0, 2.0, 15.71321743, 15.8367};
  std::vector<double> f = {1.0, 0.4, 0.05, 0.001};
  double norm = 0.0;
  for (std::size_t i = 0; i < f.size(); ++i)
    norm += f[i] * (2.0 / 3.0) *
        (std::pow(edges[i + 1], 1.5) - std::pow(edges[i], 1.5));
  for (auto & v : f)
    v /= norm;
  const auto shape = reconstructConservativeSubcells(edges, f);
  double reconstructed_mass = 0.0;
  for (std::size_t i = 0; i < f.size(); ++i)
  {
    const double a = edges[i], b = edges[i + 1];
    const double mu = shape.mass_centroids_eV[i];
    const double slope = shape.relative_slopes_per_eV[i];
    require(1.0 + slope * (a - mu) >= -1e-12 &&
            1.0 + slope * (b - mu) >= -1e-12,
            "P0-3: subcell f0 is negative");
    const double mass = shape.cell_number_masses[i];
    const double moment = (2.0 / 5.0) *
        (std::pow(b, 2.5) - std::pow(a, 2.5));
    reconstructed_mass += f[i] * (mass + slope * (moment - mu * mass));
  }
  require(std::abs(reconstructed_mass - 1.0) < 1e-12,
          "P0-3: sqrt(E)-weighted mass not conserved");

  const std::vector<double> energy = {0.0, 15.8, 16.0};
  const std::vector<double> sigma = {0.0, 0.0, 2e-22};
  const double a = 15.8, b = 15.8367;
  const double mu = shape.mass_centroids_eV.back();
  const double slope = shape.relative_slopes_per_eV.back();
  const double reconstructed = integrateSubcellEnergyCrossSection(
      energy, sigma, a, b, mu, slope);
  const double constant = integrateSubcellEnergyCrossSection(
      energy, sigma, a, b, mu, 0.0);
  double midpoint_oracle = 0.0;
  constexpr std::size_t quadrature = 100000;
  for (std::size_t j = 0; j < quadrature; ++j)
  {
    const double E = a + (static_cast<double>(j) + 0.5) *
        (b - a) / static_cast<double>(quadrature);
    midpoint_oracle += E * 1e-21 * (E - a) *
        (1.0 + slope * (E - mu)) *
        (b - a) / static_cast<double>(quadrature);
  }
  require(reconstructed > 0.0 && reconstructed < constant &&
          std::abs(reconstructed - midpoint_oracle) / reconstructed < 1e-9,
          "P0-3: exact near-threshold integral failed manufactured oracle");

  ElasticInput thin;
  thin.max_energy_eV = edges.back();
  thin.cells = f.size();
  thin.energy_cell_edges_eV = edges;
  thin.targets = {{"synthetic-neutral", 1.0, 1.37e-5,
                   {0.0, 16.0}, {5e-20, 5e-20}}};
  const std::vector<IonizationChannel> near_ions = {
      {"synthetic-threshold-ion", "synthetic-neutral", 15.8, energy, sigma}};
  const std::vector<AttachmentChannel> near_att = {
      {"synthetic-attachment", "synthetic-neutral",
       {0.0, 16.0}, {1e-26, 1e-26}}};
  const auto op = assembleGrowthCollisions(thin, near_ions, near_att, f);
  require(op.maximum_number_balance_relative_error < 1e-9,
          "P0-3: reconstructed gain/loss number ledger failed");
  const double gamma = std::sqrt(2.0 * 1.602176634e-19 / 9.1093837139e-31);
  require(std::abs(op.ionization_event_columns.back() - gamma * reconstructed) <
              1e-10 * gamma * reconstructed,
          "P0-3: donor ionization coefficient disagrees with exact subcell integral");
  for (std::size_t donor = 0; donor < f.size(); ++donor)
  {
    double column_sum = 0.0;
    for (const auto & entry : op.entries)
      if (entry.donor == donor)
        column_sum += entry.coefficient_m3_per_s;
    const double expected = op.ionization_event_columns[donor] -
                            op.attachment_event_columns[donor];
    const double scale = op.ionization_event_columns[donor] +
                         op.attachment_event_columns[donor];
    require(scale > 0.0 && std::abs(column_sum - expected) < 1e-9 * scale,
            "P0-3: equal-sharing source/attachment column balance failed");
  }
  ElasticResult frozen;
  frozen.eepf_eV_minus_3_halves = f;
  frozen.energy_eV = energyMeshCenters(edges);
  const auto rate = evaluateGrowthOnFrozenEepf(thin, frozen, near_ions, near_att, f);
  require(std::abs(rate.ionization_rates_m3_per_s[0] -
                   gamma * f.back() * reconstructed) <
              1e-10 * gamma * f.back() * reconstructed &&
          rate.operator_number_balance_relative_error < 1e-9,
          "P0-3: reconstructed rate and actual collision Q disagree");

  rejects([&] { auto bad = f; bad.back() = -1.0;
                 (void)reconstructConservativeSubcells(edges, bad); });
  rejects([&] { auto bad = f; bad.front() *= 2.0;
                 (void)reconstructConservativeSubcells(edges, bad); });
  rejects([&] { (void)integrateSubcellEnergyCrossSection(
                    energy, sigma, a, b, mu, -1e6); });

  // Actual compiled M6b coupled ion/attachment/excitation eigen re-solves.
  // Only growth Q is reconstructed; M5 excitation is still cell constant.
  ElasticInput input;
  input.reduced_field_Td = 0.05;
  input.gas_temperature_K = 1000.0;
  input.max_energy_eV = 4.0;
  input.cells = 36;
  input.targets = {{"synthetic-neutral", 1.0, 1.37e-5,
                    {0.0, 16.0}, {5e-20, 5e-20}}};
  const std::vector<IonizationChannel> ions = {
      {"synthetic-ion", "synthetic-neutral", 0.5,
       {0.0, 0.5, 16.0}, {0.0, 0.0, 1e-25}}};
  const std::vector<AttachmentChannel> attaches = {
      {"synthetic-attachment", "synthetic-neutral",
       {0.0, 16.0}, {1e-26, 1e-26}}};
  const std::vector<ExcitationChannel> excitations = {
      {"synthetic-excitation", "synthetic-neutral", 0.8,
       {0.0, 0.8, 16.0}, {0.0, 0.0, 1e-25}}};

  ReconstructedGrowthControls permissive;
  permissive.maximum_updates = 4;
  permissive.required_stable_updates = 1;
  permissive.distribution_l1_limit = 0.99;
  permissive.rate_relative_limit = 0.99;
  const auto coupled = solveTemporalGrowthWithSubcellPicard(
      input, ions, attaches, excitations, permissive);
  require(coupled.converged &&
          coupled.status == "CONVERGED_PICARD_GROWTH_ONLY_SCIENCE_HOLD" &&
          !coupled.history.empty() &&
          coupled.solution.maximum_normalized_eigen_residual < 1e-8 &&
          coupled.solution.growth.operator_number_balance_relative_error < 1e-9,
          "P0-3: actual synthetic reconstructed eigen re-solve failed");

  // Realistic numerical tolerances are tested separately from the
  // deliberately permissive state-machine control. Report the actual result,
  // whether converged or HOLD, rather than re-labeling it as physical parity.
  ReconstructedGrowthControls nominal;
  const auto nominal_result = solveTemporalGrowthWithSubcellPicard(
      input, ions, attaches, excitations, nominal);
  require(!nominal_result.history.empty() &&
          nominal_result.solution.maximum_normalized_eigen_residual < 1e-8 &&
          nominal_result.solution.growth.operator_number_balance_relative_error < 1e-9 &&
          (nominal_result.converged ?
             (nominal_result.history.back().stable &&
              nominal_result.status == "CONVERGED_PICARD_GROWTH_ONLY_SCIENCE_HOLD") :
             (nominal_result.status == "HOLD_PICARD_MAX_UPDATES")),
          "P0-3: nominal-tolerance Picard did not report a valid outcome");

  ReconstructedGrowthControls strict;
  strict.maximum_updates = 1;
  strict.required_stable_updates = 1;
  strict.distribution_l1_limit = 1e-14;
  strict.rate_relative_limit = 1e-14;
  const auto held = solveTemporalGrowthWithSubcellPicard(
      input, ions, attaches, excitations, strict);
  require(!held.converged && held.status == "HOLD_PICARD_MAX_UPDATES" &&
          held.history.size() == 1,
          "P0-3: strict nonlinear Picard tolerance failed open");
  rejects([&] { auto bad = strict; bad.maximum_updates = 0;
                 (void)solveTemporalGrowthWithSubcellPicard(
                     input, ions, attaches, excitations, bad); });

  std::cout << "P0-3 actual C++ SYNTHETIC growth-only Picard: "
            << "manufactured_threshold_ratio=" << reconstructed / constant
            << ", reconstructed_mass=" << reconstructed_mass
            << ", collision_balance=" << op.maximum_number_balance_relative_error
            << ", eigen_residual=" << coupled.solution.maximum_normalized_eigen_residual
            << ", first_Picard_L1=" << coupled.history.front().distribution_l1_change
            << ", nominal_Picard=" << nominal_result.status
            << ", nominal_updates=" << nominal_result.history.size()
            << ", nominal_final_L1=" << nominal_result.history.back().distribution_l1_change
            << ", nominal_final_rate_change=" << nominal_result.history.back().maximum_rate_relative_change
            << ", strict_HOLD=PASS; NOT BOLSIG+ PARITY\\n";
}
