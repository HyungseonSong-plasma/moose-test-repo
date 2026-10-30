// First-party synthetic data. Geometry and actual M6b nonuniform C++ solve;
// no LXCat/BOLSIG+ source rows and NO native physical-parity claim.
#include "PhysicsBoltzmannThresholdMesh.h"
#include "PhysicsBoltzmannTemporalGrowth.h"
#include "PhysicsBoltzmannEnergyMesh.h"

#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
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
void rejects(const std::function<void()> & f)
{
  try { f(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("P0-2: invalid mesh controls were accepted");
}
void holds(const std::function<void()> & f)
{
  try { f(); }
  catch (const std::runtime_error & e)
  {
    if (std::string(e.what()).find("HOLD_DENSE_REFERENCE_CELL_LIMIT") !=
        std::string::npos)
      return;
  }
  throw std::runtime_error("P0-2: dense budget failed open");
}
}

int main()
{
  ThresholdMeshControls c;
  c.maximum_cells = 256;
  const double emax = 15.8367;
  const double threshold = 15.8;
  const auto mesh = buildThresholdAwareMesh(emax, 48, {threshold, 3.0}, c);
  require(mesh.threshold_faces == 2 && mesh.edges_eV.front() == 0.0 &&
          mesh.edges_eV.back() == emax &&
          mesh.edges_eV.size() - 1 <= c.maximum_cells,
          "P0-2: threshold or domain boundary missing");
  for (std::size_t i = 1; i < mesh.edges_eV.size(); ++i)
    require(mesh.edges_eV[i] > mesh.edges_eV[i - 1],
            "P0-2: FV grid is not strictly increasing");
  std::size_t c3_cells = 0;
  for (std::size_t i = 0; i + 1 < mesh.edges_eV.size(); ++i)
    if (mesh.edges_eV[i] >= threshold)
      ++c3_cells;
  require(c3_cells >= c.threshold_side_cells,
          "P0-2: near-cutoff C3 window lacks requested subcells");
  require(mesh.edges_eV[1] < emax / 48.0,
          "P0-2: low-energy power-law refinement missing");
  require(mesh.maximum_tail_width_eV <=
          emax * c.tail_window_fraction / static_cast<double>(c.tail_cells) *
              (1.0 + 1e-10),
          "P0-2: high-energy tail width not bounded");

  rejects([&] { (void)buildThresholdAwareMesh(emax, 48, {emax}, c); });
  rejects([&] { (void)buildThresholdAwareMesh(emax, 48, {-0.1}, c); });
  rejects([&] { (void)buildThresholdAwareMesh(emax, 48, {std::numeric_limits<double>::quiet_NaN()}, c); });
  rejects([&] {
    auto bad = c;
    bad.tail_window_fraction = 1.0;
    (void)buildThresholdAwareMesh(emax, 48, {}, bad);
  });
  holds([&] {
    auto small = c;
    small.maximum_cells = 48;
    (void)buildThresholdAwareMesh(emax, 48, {threshold}, small);
  });

  ElasticInput input;
  input.reduced_field_Td = 0.05;
  input.gas_temperature_K = 1000.0;
  input.max_energy_eV = 4.0;
  input.cells = 40;
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

  const auto refined = withThresholdAwareMesh(input, {0.5, 0.8}, c);
  require(refined.cells > input.cells && refined.cells <= 256 &&
          refined.energy_cell_edges_eV.size() == refined.cells + 1,
          "P0-2: custom FV geometry was not installed");
  rejects([&] { (void)withThresholdAwareMesh(refined, {0.5}, c); });

  const auto eigen = solveElasticTemporalGrowth(
      refined, ions, attaches, excitations);
  require(eigen.maximum_normalized_eigen_residual < 1e-8 &&
          eigen.distribution.energy_cell_edges_eV ==
              refined.energy_cell_edges_eV &&
          std::isfinite(eigen.distribution.mean_energy_eV) &&
          eigen.distribution.mean_energy_eV > 0.0,
          "P0-2: real nonuniform M6b eigen solve failed");
  const auto & f = eigen.distribution.eepf_eV_minus_3_halves;
  const auto & edges = refined.energy_cell_edges_eV;
  double mass = 0.0;
  for (std::size_t i = 0; i < f.size(); ++i)
  {
    require(std::isfinite(f[i]) && f[i] >= 0.0,
            "P0-2: nonphysical eigen-EEPF");
    mass += f[i] * (2.0 / 3.0) *
        (std::pow(edges[i + 1], 1.5) - std::pow(edges[i], 1.5));
  }
  require(std::abs(mass - 1.0) < 1e-8,
          "P0-2: conservative FV EEPF normalization failed");
  const auto rates = evaluateGrowthOnFrozenEepf(
      refined, eigen.distribution, ions, attaches);
  require(rates.operator_number_balance_relative_error < 1e-9 &&
          rates.ionization_rates_m3_per_s.size() == 1 &&
          rates.attachment_rates_m3_per_s.size() == 1 &&
          rates.ionization_rates_m3_per_s[0] > 0.0 &&
          rates.attachment_rates_m3_per_s[0] > 0.0,
          "P0-2: actual growth source/gain balance failed");
  const auto excitation_rates = evaluateExcitationRatesOnEepf(
      refined, eigen.distribution, excitations);
  require(excitation_rates.forward_rates_m3_per_s.size() == 1 &&
          excitation_rates.forward_rates_m3_per_s[0] > 0.0,
          "P0-2: actual excitation rate failed");
  std::cout << "P0-2 actual C++ synthetic nonuniform M6b: C3 active cells="
            << c3_cells << ", mesh cells=" << mesh.edges_eV.size() - 1
            << ", eigen cells=" << refined.cells
            << ", mean=" << eigen.distribution.mean_energy_eV
            << " eV, mass=" << mass
            << ", eigen residual=" << eigen.maximum_normalized_eigen_residual
            << ", number balance=" << rates.operator_number_balance_relative_error
            << "; NOT BOLSIG+ PARITY\n";
}
