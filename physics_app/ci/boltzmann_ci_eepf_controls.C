// CI-only direct execution of the independently developed C++ Boltzmann solver.
// All collision cross sections are MANUFACTURED CONSTANT ELASTIC values.
// Native EEPF is authentic to this C++ implementation, but this experiment is
// NOT physically equivalent to a BOLSIG+ PHELPS/SIGLO collision inventory.
#include "PhysicsBoltzmannElasticSolver.h"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

using namespace PhysicsBoltzmann;
struct Case
{
  const char * id;
  double EN;
  double Emax;
  std::size_t cells;
  std::vector<double> fractions;
};

int main()
{
  const std::vector<Case> cases = {
    {"example1_R21", 10.0, 30.5817, 400, {0.10, 0.90}},
    {"example2_R1_DC", 100.0, 45.8595, 200, {0.99, 0.01}},
    {"example3_R31", 10.0623, 18.3760, 100, {1.00, 0.00}},
    {"example3_R33", 10.0623, 20.4016, 100, {0.50, 0.50}},
    {"example3_R35", 10.0623, 39.7141, 100, {0.00, 1.00}},
    {"example4_R1", 10.0, 15.8367, 200, {0.70, 0.20, 0.08, 0.02}},
    // True C++ cutoff sensitivity on the exact same cell width and input
    // physics. This is diagnostic evidence, never real-gas acceptance.
    {"example4_R1_Emax2x", 10.0, 31.6734, 400, {0.70, 0.20, 0.08, 0.02}},
    {"example4_R1_Emax4x", 10.0, 63.3468, 800, {0.70, 0.20, 0.08, 0.02}},
    {"example4_R1_Emax8x", 10.0, 126.6936, 1600, {0.70, 0.20, 0.08, 0.02}}
  };
  const std::vector<const char *> names = {"Ar", "He", "N2", "O2"};
  // Source-free independent synthesis: not fitted to BOLSIG+.
  const std::vector<double> sigma = {5.0e-20, 5.0e-20, 5.0e-20, 5.0e-20};
  const std::vector<double> electron_mass_ratios = {
      1.37e-5, 1.37e-4, 1.96e-5, 1.71e-5};
  std::cout << std::setprecision(std::numeric_limits<double>::max_digits10);
  for (const auto & sample : cases)
  {
    ElasticInput input;
    input.reduced_field_Td = sample.EN;
    input.gas_temperature_K = 300.0;
    input.max_energy_eV = sample.Emax;
    input.cells = sample.cells;
    for (std::size_t i = 0; i < sample.fractions.size(); ++i)
    {
      if (!(sample.fractions[i] > 0.0))
        continue;
      input.targets.push_back({names[i], sample.fractions[i],
                               electron_mass_ratios[i],
                               {0.0, sample.Emax}, {sigma[i], sigma[i]}});
    }
    const auto result = solveElasticSteadyState(input);
    if (!std::isfinite(result.mean_energy_eV) ||
        !(result.mean_energy_eV > 0.0) ||
        result.energy_eV.size() != sample.cells)
      throw std::runtime_error("CI output EEPF missing or invalid");
    std::cout << "{\"id\":\"" << sample.id << "\","
              << "\"model\":\"SYNTHETIC_ELASTIC_ONLY_NOT_BOLSIG_PARITY\","
              << "\"reduced_field_Td\":" << sample.EN << ','
              << "\"gas_temperature_K\":300,"
              << "\"max_energy_eV\":" << sample.Emax << ','
              << "\"cells\":" << sample.cells << ','
              << "\"mean_energy_eV\":" << result.mean_energy_eV << ','
              << "\"mixture\":{";
    bool delimiter = false;
    for (std::size_t i = 0; i < sample.fractions.size(); ++i)
      if (sample.fractions[i] > 0.0)
      {
        if (delimiter) std::cout << ',';
        delimiter = true;
        std::cout << '"' << names[i] << "\":" << sample.fractions[i];
      }
    std::cout << "},\"energy_eV\":[";
    for (std::size_t i = 0; i < sample.cells; ++i)
    {
      if (i) std::cout << ',';
      std::cout << result.energy_eV[i];
    }
    std::cout << "],\"eepf_eV_minus_3_halves\":[";
    for (std::size_t i = 0; i < sample.cells; ++i)
    {
      if (i) std::cout << ',';
      const auto v = result.eepf_eV_minus_3_halves[i];
      if (!std::isfinite(v) || v < 0.0)
        throw std::runtime_error("CI output EEPF negative/nonfinite");
      std::cout << v;
    }
    std::cout << "]}\n";
  }
  return 0;
}
