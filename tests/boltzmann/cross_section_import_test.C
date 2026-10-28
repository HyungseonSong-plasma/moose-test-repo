#include "PhysicsBoltzmannCrossSections.h"

#include <cmath>
#include <functional>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

using namespace PhysicsBoltzmann;

static void rejects(const std::function<void()> & test)
{
  try { test(); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("expected BOLSIG collision-file rejection");
}

static std::string fixture()
{
  // Entirely authored synthetic data: no published Ar/O2 values are present.
  return "SYNTHETIC TEST ONLY (NOT LXCAT)\n"
         "ELASTIC\nAr\n1.3700e-5\n"
         "Reference: synthetic elastic check\n------\n"
         "0.0 5e-20\n1.0 5e-20\n2.0 5e-20\n------\n"
         "ELASTIC\nO2\n1.7e-5\n"
         "Reference: synthetic oxygen-labeled fixture\n------\n"
         "0.0 6e-20\n1.0 6e-20\n2.0 6e-20\n------\n"
         "EXCITATION\nAr -> Ar_test_excited\n0.27\n"
         "Reference: synthetic, piecewise-linear excitation\n------\n"
         "0.0 0.0\n1.0 1e-20\n2.0 2e-20\n------\n";
}

int main()
{
  std::istringstream source(fixture());
  auto file = parseBolsigCrossSections(source);
  if (!(file.header.size() == 1 && file.records.size() == 3 &&
        file.records[0].kind == CollisionKind::Elastic &&
        file.records[2].kind == CollisionKind::Excitation &&
        file.records[2].product == "Ar_test_excited" &&
        file.records[2].comments.size() == 1 &&
        file.records[2].source_line > file.records[0].source_line))
    throw std::runtime_error("BOLSIG parser lost typed process or citation data");

  const std::map<std::string, double> fractions = {{"Ar", 0.65}, {"O2", 0.35}};
  const auto imported = prepareElasticExcitation(file, fractions, 2.0);
  if (!(imported.targets.size() == 2 && imported.channels.size() == 1 &&
        imported.channels[0].threshold_eV == 0.27 &&
        imported.channels[0].target_name == "Ar" &&
        imported.targets[1].mole_fraction == 0.35))
    throw std::runtime_error("BOLSIG import changed physics input");

  ElasticInput input;
  input.cells = 125;
  input.max_energy_eV = 2.0;
  input.reduced_field_Td = 0.2;
  input.gas_temperature_K = 300.0;
  input.targets = imported.targets;
  const auto imported_result = solveExcitationSteadyState(input, imported.channels,
                                       ExcitationLinearMethod::SparseBiCGSTAB);
  if (!(imported_result.distribution.mean_energy_eV > 0.0 &&
        imported_result.maximum_collision_number_balance_error < 1e-9 &&
        imported_result.maximum_normalized_equation_residual < 1e-8 &&
        imported_result.rate_coefficients_m3_per_s[0] > 0.0))
    throw std::runtime_error("BOLSIG import cannot feed conservative C++ energy solver");

  // Control: direct C++ objects must reproduce the imported-input state.
  ElasticInput direct = input;
  direct.targets = {
      {"Ar", 0.65, 1.37e-5, {0.0, 1.0, 2.0}, {5e-20, 5e-20, 5e-20}},
      {"O2", 0.35, 1.7e-5, {0.0, 1.0, 2.0}, {6e-20, 6e-20, 6e-20}}};
  ExcitationChannel xc{"Ar:excitation:1", "Ar", 0.27,
                       {0.0, 1.0, 2.0}, {0.0, 1e-20, 2e-20}};
  const auto control = solveExcitationSteadyState(direct, {xc},
                                       ExcitationLinearMethod::SparseBiCGSTAB);
  const double scalar_difference = std::abs(
      imported_result.distribution.mean_energy_eV - control.distribution.mean_energy_eV);
  if (scalar_difference > 1e-13)
    throw std::runtime_error("BOLSIG parsed-input mean energy differs from direct independent input");

  auto mutate = [&](const std::string & from, const std::string & to)
  {
    std::string text = fixture();
    const auto pos = text.find(from);
    if (pos == std::string::npos)
      throw std::runtime_error("missing fixture mutation anchor");
    text.replace(pos, from.size(), to);
    return text;
  };
  rejects([&] { std::istringstream f(mutate("ELASTIC\nAr", "EFFECTIVE\nAr"));
                 (void)prepareElasticExcitation(parseBolsigCrossSections(f), fractions, 2.0); });
  rejects([&] { std::istringstream f(mutate("EXCITATION\n", "IONIZATION\n"));
                 (void)prepareElasticExcitation(parseBolsigCrossSections(f), fractions, 2.0); });
  rejects([&] { std::istringstream f(mutate("Ar -> Ar_test_excited", "Ar <-> Ar_test_excited"));
                 (void)prepareElasticExcitation(parseBolsigCrossSections(f), fractions, 2.0); });
  rejects([&] { std::istringstream f(mutate("1.0 1e-20\n2.0 2e-20", "1.0 1e-20\n0.9 2e-20"));
                 (void)parseBolsigCrossSections(f); });
  rejects([&] { std::istringstream f(mutate("2.0 2e-20", "2.0 -2e-20"));
                 (void)parseBolsigCrossSections(f); });
  rejects([&] { std::istringstream f(mutate("2.0 2e-20", "2.0 NaN"));
                 (void)parseBolsigCrossSections(f); });
  rejects([&] { std::istringstream f(mutate("0.27", "-0.27"));
                 (void)parseBolsigCrossSections(f); });
  rejects([&] { (void)prepareElasticExcitation(file, {{"Ar", 1.0}}, 2.0); });
  rejects([&] { (void)prepareElasticExcitation(file, fractions, 3.0); });
  rejects([&] { (void)prepareElasticExcitation(file, {{"Ar", 0.7}, {"O2", 0.7}}, 2.0); });
  rejects([&] { std::istringstream f(mutate("2.0 2e-20\n------", "2.0 2e-20\n"));
                 (void)parseBolsigCrossSections(f); });
  std::cout << "BOLTZMANN_BOLSIG_IMPORT_M4_P0_P1_PASS\n"
            << "BOLTZMANN_IMPORT_MEAN_EV=" << imported_result.distribution.mean_energy_eV << '\n'
            << "BOLTZMANN_IMPORT_NUMBER_BALANCE=" <<
                 imported_result.maximum_collision_number_balance_error << '\n';
}
