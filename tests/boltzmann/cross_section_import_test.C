#include "PhysicsBoltzmannCrossSections.h"

#include <algorithm>
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
        imported_result.rate_coefficients_m3_per_s[0] > 0.0 &&
        imported_result.superelastic_rate_coefficients_m3_per_s.size() == 1 &&
        imported_result.superelastic_rate_coefficients_m3_per_s[0] == 0.0 &&
        std::abs(imported_result.net_energy_loss_coefficients_eV_m3_per_s[0] -
                 0.65 * 0.27 * imported_result.rate_coefficients_m3_per_s[0]) <
            1e-13 * imported_result.rate_coefficients_m3_per_s[0]))
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
  // EFFECTIVE includes excitation momentum. This synthetic table is
  // exactly elastic + excitation, so both representations must yield the
  // same EEPF, rates, and conservative balance.
  std::string effective_text = mutate("ELASTIC\nAr", "EFFECTIVE\nAr");
  const std::string original_table =
      "0.0 5e-20\n1.0 5e-20\n2.0 5e-20\n";
  const auto table_at = effective_text.find(original_table);
  if (table_at == std::string::npos)
    throw std::runtime_error("effective momentum fixture anchor missing");
  effective_text.replace(table_at, original_table.size(),
                         "0.0 5e-20\n1.0 6e-20\n2.0 7e-20\n");
  std::istringstream effective_stream(effective_text);
  const auto effective_input = prepareElasticExcitation(
      parseBolsigCrossSections(effective_stream), fractions, 2.0);
  if (effective_input.targets.size() != 2 ||
      effective_input.channels.size() != 1)
    throw std::runtime_error("EFFECTIVE target projection missing");
  ElasticInput effective_conditions = input;
  effective_conditions.targets = effective_input.targets;
  const auto effective_result = solveExcitationSteadyState(
      effective_conditions, effective_input.channels,
      ExcitationLinearMethod::SparseBiCGSTAB);
  if (!(std::abs(imported_result.distribution.mean_energy_eV -
                 effective_result.distribution.mean_energy_eV) < 1e-10 &&
        std::abs(imported_result.rate_coefficients_m3_per_s[0] -
                 effective_result.rate_coefficients_m3_per_s[0]) <
                 1e-9 * imported_result.rate_coefficients_m3_per_s[0] &&
        effective_result.maximum_normalized_equation_residual < 1e-8 &&
        effective_result.maximum_collision_number_balance_error < 1e-9))
    throw std::runtime_error(
        "EFFECTIVE reconstruction double-counted excitation momentum");
  // Reject an impossible negative elastic remainder.
  rejects([&] {
    std::string invalid = effective_text;
    const auto bad = invalid.find("2.0 7e-20");
    if (bad == std::string::npos)
      throw std::runtime_error("bad effective mutation anchor");
    invalid.replace(bad, std::string("2.0 7e-20").size(), "2.0 1e-21");
    std::istringstream f(invalid);
    (void)prepareElasticExcitation(parseBolsigCrossSections(f), fractions, 2.0);
  });
  // Two momentum providers for one target must never be combined.
  rejects([&] {
    std::string invalid = effective_text +
        "ELASTIC\nAr\n1.3700e-5\n------\n"
        "0.0 5e-20\n2.0 5e-20\n------\n";
    std::istringstream f(invalid);
    (void)prepareElasticExcitation(parseBolsigCrossSections(f), fractions, 2.0);
  });
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
  // M5 synthetic reversible Ar <-> Ar*: the BOLSIG+ third-line second
  // number is g_upper/g_lower. The excited-state elastic data AND fractional
  // population must both be supplied; there is no implicit excited fallback.
  const double theta = 1.380649e-23 * 12000.0 / 1.602176634e-19;
  const double inverse_ratio = 2.0 * std::exp(-0.4 / theta);
  const double lower_fraction = 1.0 / (1.0 + inverse_ratio);
  const double upper_fraction = 1.0 - lower_fraction;
  const std::string reversible_text =
      "SYNTHETIC DEGENERACY TEST, NOT AR CROSS SECTIONS\n"
      "ELASTIC\nAr\n1.37e-5\nsource: synthetic ground\n------\n"
      "0 5e-20\n10 5e-20\n------\n"
      "ELASTIC\nAr*\n1.37e-5\nsource: synthetic upper\n------\n"
      "0 5e-20\n10 5e-20\n------\n"
      "EXCITATION\nAr <-> Ar*\n0.4 2.0\n"
      "source: synthetic threshold\n------\n"
      "0 0\n0.4 0\n0.401 1e-20\n10 1e-20\n------\n";
  std::istringstream reverse_source(reversible_text);
  auto reverse_file = parseBolsigCrossSections(reverse_source);
  const std::map<std::string, double> reverse_fractions =
      {{"Ar", lower_fraction}, {"Ar*", upper_fraction}};
  if (!(reverse_file.records.size() == 3 &&
        reverse_file.records[2].reversible &&
        reverse_file.records[2].upper_to_lower_weight_ratio == 2.0))
    throw std::runtime_error("BOLSIG reversible statistical-weight metadata lost");
  rejects([&] { (void)prepareElasticExcitation(reverse_file, reverse_fractions, 10.0); });
  const auto reversible = prepareElasticExcitation(
      reverse_file, reverse_fractions, 10.0, true);
  if (!(reversible.channels.size() == 1 &&
        reversible.channels[0].upper_state_target_name == "Ar*" &&
        reversible.channels[0].upper_to_lower_weight_ratio == 2.0))
    throw std::runtime_error("reversible excited state projection mismatch");
  ElasticInput equilibrium_input;
  equilibrium_input.max_energy_eV = 10.0;
  equilibrium_input.cells = 125; // excitation threshold aligns with 0.08 eV cells
  equilibrium_input.gas_temperature_K = 12000.0;
  equilibrium_input.reduced_field_Td = 0.0;
  equilibrium_input.targets = reversible.targets;
  const auto thermal_dense = solveExcitationSteadyState(
      equilibrium_input, reversible.channels, ExcitationLinearMethod::DenseReference);
  const auto thermal_sparse = solveExcitationSteadyState(
      equilibrium_input, reversible.channels, ExcitationLinearMethod::SparseBiCGSTAB);
  const double relative_mean_error = std::abs(
      thermal_dense.distribution.mean_energy_eV - 1.5 * theta) / (1.5 * theta);
  const double forward_events =
      lower_fraction * thermal_dense.rate_coefficients_m3_per_s[0];
  const double inverse_events =
      upper_fraction * thermal_dense.superelastic_rate_coefficients_m3_per_s[0];
  const double rate_balance = std::abs(forward_events - inverse_events) / forward_events;
  const double net_energy = thermal_dense.net_energy_loss_coefficients_eV_m3_per_s[0];
  if (!(relative_mean_error < 0.025 &&
        rate_balance < 0.025 &&
        std::abs(net_energy) < 0.025 * 0.4 * forward_events &&
        thermal_dense.maximum_collision_number_balance_error < 1e-9 &&
        thermal_dense.maximum_normalized_equation_residual < 1e-8))
    throw std::runtime_error("superelastic zero-field Maxwellian detailed balance failed");
  if (!(std::abs(thermal_dense.distribution.mean_energy_eV -
                 thermal_sparse.distribution.mean_energy_eV) < 1e-7 &&
        std::abs(thermal_dense.rate_coefficients_m3_per_s[0] -
                 thermal_sparse.rate_coefficients_m3_per_s[0]) <
                 1e-7 * thermal_dense.rate_coefficients_m3_per_s[0] &&
        thermal_sparse.maximum_normalized_equation_residual < 1e-8))
    throw std::runtime_error("M5 superelastic dense/sparse parity failed");

  // Negative control: an EFFECTIVE momentum record for the upper state
  // may already include superelastic scattering, and cannot be converted
  // into an elastic record by subtracting only forward excitation.
  rejects([&] {
    std::string invalid = reversible_text;
    const auto upper = invalid.find("ELASTIC\nAr*\n");
    if (upper == std::string::npos)
      throw std::runtime_error("missing excited target fixture anchor");
    invalid.replace(upper, std::string("ELASTIC").size(), "EFFECTIVE");
    std::istringstream f(invalid);
    (void)prepareElasticExcitation(
        parseBolsigCrossSections(f), reverse_fractions, 10.0, true);
  });

  // Negative controls: no excited-state elastic record, absent upper target,
  // nonphysical degeneracy, and missing explicit upper-state composition.
  rejects([&] {
    std::istringstream f(reversible_text);
    (void)prepareElasticExcitation(parseBolsigCrossSections(f),
                                  {{"Ar", 1.0}}, 10.0, true);
  });
  rejects([&] {
    auto m = reversible.channels;
    m[0].upper_to_lower_weight_ratio = 0.0;
    (void)solveExcitationSteadyState(equilibrium_input, m);
  });
  rejects([&] {
    const auto source = mutate("EXCITATION\n", "IONIZATION\n");
    std::istringstream f(source);
    (void)prepareElasticExcitation(parseBolsigCrossSections(f), fractions, 2.0, true);
  });
  // M6b3: complete ELASTIC and EFFECTIVE descriptions of the SAME
  // invented excitation + ionization + attachment mixture. For ELASTIC
  // source, the field momentum must include all three inelastic channels;
  // for EFFECTIVE source, their sum must be subtracted from recoil ONCE.
  // This is synthetic operator equivalence, NOT BOLSIG+ reference parity.
  const std::string changing =
      "EXCITATION\nAr -> Ar_exc\n0.4\nsynthetic\n------\n"
      "0 0\n0.4 0\n1 1e-20\n1.2 1e-20\n2 1e-20\n------\n"
      "IONIZATION\nAr -> Ar+\n1.2\nsynthetic\n------\n"
      "0 0\n1.2 0\n2 5e-21\n------\n"
      "ATTACHMENT\nAr -> Ar-\nsynthetic\n------\n"
      "0 2e-21\n2 2e-21\n------\n";
  const std::string elastic_growth =
      "ELASTIC\nAr\n1.37e-5\nsynthetic\n------\n"
      "0 5e-20\n2 5e-20\n------\n" + changing;
  const std::string effective_growth =
      "EFFECTIVE\nAr\n1.37e-5\nsynthetic\n------\n"
      "0 5.2e-20\n0.4 5.2e-20\n1 6.2e-20\n"
      "1.2 6.2e-20\n2 6.7e-20\n------\n" + changing;
  std::istringstream elastic_growth_stream(elastic_growth);
  std::istringstream effective_growth_stream(effective_growth);
  const auto whole_elastic = prepareGrowthPhysics(
      parseBolsigCrossSections(elastic_growth_stream), {{"Ar", 1.0}}, 2.0);
  const auto whole_effective = prepareGrowthPhysics(
      parseBolsigCrossSections(effective_growth_stream), {{"Ar", 1.0}}, 2.0);
  if (!(whole_elastic.targets.size() == 1 && whole_effective.targets.size() == 1 &&
        whole_effective.excitation_channels.size() == 1 &&
        whole_effective.ionization_channels.size() == 1 &&
        whole_effective.attachment_channels.size() == 1 &&
        !whole_elastic.targets[0].field_momentum_transfer_m2.empty() &&
        !whole_effective.targets[0].field_momentum_transfer_m2.empty()))
    throw std::runtime_error("M6b3 full scattering inventory not retained");
  const auto & a_target = whole_elastic.targets[0];
  const auto & b_target = whole_effective.targets[0];
  if (a_target.energy_eV != b_target.energy_eV)
    throw std::runtime_error("M6b3 knot unions differ");
  for (std::size_t k = 0; k < a_target.energy_eV.size(); ++k)
  {
    const double rebound = a_target.momentum_transfer_m2[k];
    const double converted = b_target.momentum_transfer_m2[k];
    const double total_a = a_target.field_momentum_transfer_m2[k];
    const double total_b = b_target.field_momentum_transfer_m2[k];
    if (!(std::abs(rebound - converted) < 1e-30 &&
          std::abs(total_a - total_b) < 1e-30))
      throw std::runtime_error("M6b3 recoil or first-harmonic scattering double counted");
  }
  ElasticInput growth_a, growth_b;
  growth_a.reduced_field_Td = 0.2;
  growth_a.gas_temperature_K = 300.0;
  growth_a.max_energy_eV = 2.0;
  growth_a.cells = 80;
  growth_a.targets = whole_elastic.targets;
  growth_b = growth_a;
  growth_b.targets = whole_effective.targets;
  const auto elastic_operator = solveExcitationSteadyState(
      growth_a, whole_elastic.excitation_channels, ExcitationLinearMethod::DenseReference);
  const auto effective_operator = solveExcitationSteadyState(
      growth_b, whole_effective.excitation_channels, ExcitationLinearMethod::DenseReference);
  if (!(std::abs(elastic_operator.distribution.mean_energy_eV -
                 effective_operator.distribution.mean_energy_eV) < 1e-9 &&
        elastic_operator.maximum_normalized_equation_residual < 1e-8 &&
        effective_operator.maximum_normalized_equation_residual < 1e-8))
    throw std::runtime_error("M6b3 ELASTIC/EFFECTIVE EEPF equivalence failed");

  // All nonelastic momentum contributors must be present: removing the
  // ionization source from EFFECTIVE input must change recoil, never match.
  rejects([&] {
    std::string invalid = effective_growth;
    const auto at = invalid.find("2 6.7e-20");
    if (at == std::string::npos)
      throw std::runtime_error("M6b3 invalid fixture anchor");
    invalid.replace(at, std::string("2 6.7e-20").size(), "2 5e-21");
    std::istringstream stream(invalid);
    (void)prepareGrowthPhysics(parseBolsigCrossSections(stream), {{"Ar", 1.0}}, 2.0);
  });
  // S11 BOLSIG+ 07/2024 manual boundary semantics (invented values).
  // The 1.5x continuation MUST be represented as linear knot segments:
  // analytic log(E)/E evaluation between nodes is not equivalent.
  const std::string boundary_source =
      "ELASTIC\nAr\n1.37e-5\nsynthetic\n------\n"
      "0.5 5e-20\n5 5e-20\n------\n"
      "EXCITATION\nAr -> test\n0.4\nsynthetic\n------\n"
      "0.3 1e-20\n0.6 3e-20\n5 3e-20\n------\n"
      "IONIZATION\nAr -> Ar+\n19.8\nsynthetic\n------\n"
      "19.9 3e-20\n25 3e-20\n------\n"
      "ATTACHMENT\nAr -> Ar-\nsynthetic\n------\n"
      "0.2 2e-21\n5 2e-21\n------\n";
  std::istringstream boundary_stream(boundary_source);
  const auto raw_boundary = parseBolsigCrossSections(boundary_stream);
  const auto manual = normalizeBolsig2024CollisionFile(raw_boundary, 10.0, true);
  if (manual.records.size() != 4)
    throw std::runtime_error("BOLSIG 2024 normalization silently dropped processes");
  const auto & elastic = manual.records[0];
  const auto & exc = manual.records[1];
  const auto & inactive_ion = manual.records[2];
  const auto & att = manual.records[3];
  const auto close = [](double a, double b)
  { return std::abs(a - b) < 1e-11 * std::max({std::abs(a), std::abs(b), 1e-30}); };
  if (!(elastic.energy_eV.front() == 0.0 &&
        close(elastic.cross_section_m2.front(), 5e-20) &&
        exc.energy_eV[0] == 0.0 && exc.energy_eV[1] == 0.4 &&
        exc.cross_section_m2[0] == 0.0 && exc.cross_section_m2[1] == 0.0 &&
        exc.energy_eV[2] == 0.6 && close(exc.cross_section_m2[2], 3e-20) &&
        inactive_ion.parameter == 19.8 &&
        inactive_ion.cross_section_m2.front() == 0.0 &&
        att.energy_eV.front() == 0.0 &&
        close(att.cross_section_m2.front(), 2e-21)))
    throw std::runtime_error("BOLSIG 2024 threshold or lower-bound preprocessing incorrect");
  const auto & e = exc.energy_eV;
  const auto & sigma = exc.cross_section_m2;
  if (!(e[e.size()-2] == 7.5 && e.back() == 11.25 &&
        close(sigma[sigma.size()-2],
              3e-20 * (std::log(7.5)/7.5) / (std::log(5.0)/5.0)) &&
        close(sigma.back(),
              3e-20 * (std::log(11.25)/11.25) / (std::log(5.0)/5.0))))
    throw std::runtime_error("BOLSIG 2024 log(E)/E 1.5x knot extension incorrect");
  const auto unchanged = normalizeBolsig2024CollisionFile(raw_boundary, 10.0, false);
  if (!(unchanged.records[1].energy_eV.back() == 5.0 &&
        raw_boundary.records[1].energy_eV.front() == 0.3 &&
        raw_boundary.records[1].cross_section_m2.front() == 1e-20))
    throw std::runtime_error("BOLSIG 2024 no-extrapolate / original-source immutability failed");
  rejects([&] {
    auto invalid = raw_boundary;
    invalid.records[0].energy_eV = {0.5, 0.9};
    invalid.records[0].cross_section_m2 = {5e-20, 5e-20};
    (void)normalizeBolsig2024CollisionFile(invalid, 10.0, true);
  });
  std::cout << "BOLTZMANN_2024_BOUNDARY_THRESHOLD_EXTRAPOLATION_P0_P1_PASS\n";
  std::cout << "BOLTZMANN_M6B3_FULL_MOMENTUM_SYNTHETIC_P0_P1_PASS\n";

  std::cout << "BOLTZMANN_SUPERELASTIC_M5_P0_P1_PASS\n"
            << "M5_MAXWELL_RELATIVE_MEAN_ERROR=" << relative_mean_error << '\n'
            << "M5_DETAILED_BALANCE_RELATIVE_ERROR=" << rate_balance << '\n';
  std::cout << "BOLTZMANN_BOLSIG_IMPORT_M4_P0_P1_PASS\n"
            << "BOLTZMANN_IMPORT_MEAN_EV=" << imported_result.distribution.mean_energy_eV << '\n'
            << "BOLTZMANN_IMPORT_NUMBER_BALANCE=" <<
                 imported_result.maximum_collision_number_balance_error << '\n';
}
