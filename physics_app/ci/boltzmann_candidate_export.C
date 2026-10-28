// Experimental developer-only runner: imported BOLSIG-format data -> one
// candidate EEPF/rate JSON. No MOOSE app objects, no third-party data bundled.
// Actual source hash/rights must be verified by independent case preflight.
#include "PhysicsBoltzmannCrossSections.h"
#include "PhysicsBoltzmannTemporalGrowth.h"
#include "PhysicsBoltzmannTransport.h"

#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>

using namespace PhysicsBoltzmann;

namespace
{
double parseNumber(const std::string & token)
{
  std::size_t pos = 0;
  const double value = std::stod(token, &pos);
  if (pos != token.size() || !std::isfinite(value))
    throw std::invalid_argument("invalid numeric command-line argument");
  return value;
}

std::size_t parseCells(const std::string & token)
{
  const double value = parseNumber(token);
  if (value < 2 || value > 16384 || std::floor(value) != value)
    throw std::invalid_argument("energy cell count outside [2,16384]");
  return static_cast<std::size_t>(value);
}

void requireSourceHash(const std::string & sha)
{
  if (sha.size() != 64 || sha.find_first_not_of("0123456789abcdef") != std::string::npos)
    throw std::invalid_argument("collision source SHA256 must be 64 lowercase hexadecimal digits");
}

void escapeJsonString(std::ostream & out, const std::string & s)
{
  out << '"';
  for (const unsigned char ch : s)
  {
    if (ch == '"' || ch == '\\')
      out << '\\' << static_cast<char>(ch);
    else if (ch < 32 || ch > 126)
      throw std::invalid_argument("JSON process identifiers must be printable ASCII");
    else
      out << static_cast<char>(ch);
  }
  out << '"';
}
} // namespace

int main(int argc, char ** argv)
{
  try
  {
    if (argc < 8)
      throw std::invalid_argument(
          "usage: boltzmann_candidate_export SOURCE_TXT SHA256 EoverN_Td Tg_K "
          "emax_eV CELLS species=fraction [species=fraction ...] [--enable-superelastic] [--diagnose-frozen-growth] [--solve-elastic-temporal-growth] [--report-elastic-transport]");

    const std::string source_path = argv[1], source_sha = argv[2];
    requireSourceHash(source_sha);
    const double EN = parseNumber(argv[3]);
    const double Tg = parseNumber(argv[4]);
    const double emax = parseNumber(argv[5]);
    const auto cells = parseCells(argv[6]);

    std::map<std::string, double> fraction;
    bool enable_superelastic = false;
    bool frozen_growth = false;
    bool temporal_growth = false;
    bool elastic_transport = false;
    for (int i = 7; i < argc; ++i)
    {
      const std::string pair = argv[i];
      if (pair == "--enable-superelastic")
      {
        if (enable_superelastic)
          throw std::invalid_argument("duplicate superelastic opt-in");
        enable_superelastic = true;
        continue;
      }
      if (pair == "--diagnose-frozen-growth")
      {
        if (frozen_growth)
          throw std::invalid_argument("duplicate frozen-growth diagnostic opt-in");
        frozen_growth = true;
        continue;
      }
      if (pair == "--solve-elastic-temporal-growth")
      {
        if (temporal_growth)
          throw std::invalid_argument("duplicate temporal growth solver option");
        temporal_growth = true;
        continue;
      }
      if (pair == "--report-elastic-transport")
      {
        if (elastic_transport)
          throw std::invalid_argument("duplicate elastic-transport moment option");
        elastic_transport = true;
        continue;
      }
      const auto pos = pair.find('=');
      if (pos == std::string::npos || pos == 0 || pos + 1 >= pair.size())
        throw std::invalid_argument("gas composition requires species=fraction");
      const auto species = pair.substr(0, pos);
      if (!fraction.emplace(species, parseNumber(pair.substr(pos + 1))).second)
        throw std::invalid_argument("duplicate target fraction");
    }
    if (!std::isfinite(EN) || EN < 0 || !(Tg > 0) || !(emax > 0))
      throw std::invalid_argument("invalid gas temperature, energy ceiling or E/N");

    if (elastic_transport && (temporal_growth || frozen_growth || enable_superelastic))
      throw std::invalid_argument("elastic transport-only moments incompatible with particle growth or superelastic");
    if (temporal_growth && (frozen_growth || enable_superelastic))
      throw std::invalid_argument("temporal elastic-growth solver is incompatible with frozen growth/superelastic");
    std::ifstream stream(source_path);
    if (!stream.good())
      throw std::invalid_argument("cannot open collision source file");
    auto file = parseBolsigCrossSections(stream);
    std::vector<ElasticTarget> targets;
    std::vector<ExcitationChannel> excitation;
    std::vector<IonizationChannel> ionizations;
    std::vector<AttachmentChannel> attachments;
    if (frozen_growth || temporal_growth)
    {
      auto projected = prepareGrowthPhysics(file, fraction, emax, enable_superelastic);
      if (temporal_growth && !projected.excitation_channels.empty())
        throw std::invalid_argument("elastic temporal-growth eigen solver does not include excitation");
      targets = std::move(projected.targets);
      excitation = std::move(projected.excitation_channels);
      ionizations = std::move(projected.ionization_channels);
      attachments = std::move(projected.attachment_channels);
    }
    else
    {
      auto projected = prepareElasticExcitation(file, fraction, emax, enable_superelastic);
      targets = std::move(projected.targets);
      excitation = std::move(projected.channels);
    }

    if (elastic_transport && (!excitation.empty() || !ionizations.empty() ||
                              !attachments.empty()))
      throw std::invalid_argument("M7a requires elastic-only scattering and no inelastic channels");

    ElasticInput conditions;
    conditions.cells = cells;
    conditions.max_energy_eV = emax;
    conditions.gas_temperature_K = Tg;
    conditions.reduced_field_Td = EN;
    conditions.targets = std::move(targets);
    const auto result = excitation.empty() ?
        ExcitationResult{} : solveExcitationSteadyState(
            conditions, excitation, ExcitationLinearMethod::Auto);
    // Growth-only datasets use the elastic EEPF; otherwise solve M5's
    // excitation/superelastic physics, with M6 source applied afterward.
    ElasticResult distribution = excitation.empty() ?
        solveElasticSteadyState(conditions) : result.distribution;
    TemporalGrowthResult temporal;
    if (temporal_growth)
    {
      temporal = solveElasticTemporalGrowth(conditions, ionizations, attachments);
      distribution = temporal.distribution;
    }
    if (frozen_growth && ionizations.empty() && attachments.empty())
      throw std::invalid_argument("frozen growth requested without ionization/attachment");
    GrowthDiagnostics growth;
    if (frozen_growth)
      growth = evaluateGrowthOnFrozenEepf(
          conditions, distribution, ionizations, attachments);
    if (temporal_growth)
      growth = temporal.growth;
    ElasticTransportMoments transport;
    if (elastic_transport)
      transport = evaluateElasticTransportMoments(conditions, distribution);
    if (!excitation.empty() &&
        (result.maximum_normalized_equation_residual > 1e-8 ||
         result.maximum_collision_number_balance_error > 1e-9))
      throw std::runtime_error("candidate failed Boltzmann conservation gate");

    std::cout << std::setprecision(std::numeric_limits<double>::max_digits10);
    std::cout << "{\"schema_version\":1,\"conditions\":{"
              << "\"reduced_field_Td\":" << EN
              << ",\"gas_temperature_K\":" << Tg
              << ",\"mixture\":{";
    bool comma = false;
    for (const auto & [name, part] : fraction)
    {
      if (comma) std::cout << ',';
      comma = true;
      escapeJsonString(std::cout, name);
      std::cout << ':' << part;
    }
    const std::string model = elastic_transport ? "elastic_dc_transport_moments" :
        temporal_growth ?
        "elastic_ionization_attachment_temporal_growth_eigen_dense" :
        frozen_growth ?
        (enable_superelastic ? "elastic_superelastic_frozen_growth_diagnostic" :
                               "elastic_excitation_frozen_growth_diagnostic") :
        (enable_superelastic ? "elastic_excitation_superelastic_steady_dc" :
                               "elastic_excitation_steady_dc");
    std::cout << "},\"model\":\"" << model << "\","
              << "\"collision_source_sha256\":\"" << source_sha << "\"},"
              << "\"energy_cell_edges_eV\":[";
    for (std::size_t i = 0; i <= cells; ++i)
    {
      if (i) std::cout << ',';
      std::cout << emax * static_cast<double>(i) / static_cast<double>(cells);
    }
    std::cout << "],\"eepf_eV_minus_3_halves\":[";
    for (std::size_t i = 0; i < cells; ++i)
    {
      if (i) std::cout << ',';
      std::cout << distribution.eepf_eV_minus_3_halves[i];
    }
    std::cout << "],\"mean_energy_eV\":" << distribution.mean_energy_eV
              << ",\"rates_m3_per_s\":{";
    bool any_rate = false;
    for (std::size_t i = 0; i < excitation.size(); ++i)
    {
      if (any_rate) std::cout << ',';
      any_rate = true;
      escapeJsonString(std::cout, excitation[i].name);
      std::cout << ':' << result.rate_coefficients_m3_per_s[i];
      if (!excitation[i].upper_state_target_name.empty())
      {
        std::cout << ',';
        escapeJsonString(std::cout, excitation[i].upper_state_target_name +
                                    ":superelastic:" + std::to_string(i + 1));
        std::cout << ':' << result.superelastic_rate_coefficients_m3_per_s[i];
      }
    }
    for (std::size_t i = 0; i < ionizations.size(); ++i)
    {
      if (any_rate) std::cout << ',';
      any_rate = true;
      escapeJsonString(std::cout, ionizations[i].name);
      std::cout << ':' << growth.ionization_rates_m3_per_s[i];
    }
    for (std::size_t i = 0; i < attachments.size(); ++i)
    {
      if (any_rate) std::cout << ',';
      any_rate = true;
      escapeJsonString(std::cout, attachments[i].name);
      std::cout << ':' << growth.attachment_rates_m3_per_s[i];
    }
    std::cout << '}';
    if (frozen_growth)
      std::cout << ",\"frozen_eepf_reduced_temporal_growth_m3_per_s\":"
                << growth.reduced_temporal_growth_m3_per_s
                << ",\"frozen_eepf_ionization_energy_loss_eV_m3_per_s\":"
                << growth.reduced_ionization_energy_loss_eV_m3_per_s;
    if (temporal_growth)
      std::cout << ",\"reduced_temporal_growth_eigenvalue_m3_per_s\":"
                << temporal.reduced_growth_eigenvalue_m3_per_s
                << ",\"generalized_eigen_residual\":"
                << temporal.maximum_normalized_eigen_residual
                << ",\"eigen_inverse_iterations\":"
                << temporal.inverse_iterations;
    if (elastic_transport)
      std::cout << ",\"elastic_transport\":{"
                << "\"mobility_times_N_per_m_V_s\":"
                << transport.reduced_mobility_N_per_m_V_s
                << ",\"diffusion_times_N_per_m_s\":"
                << transport.reduced_diffusion_N_per_m_s
                << ",\"energy_mobility_times_N_per_m_V_s\":"
                << transport.reduced_energy_mobility_N_per_m_V_s
                << ",\"energy_diffusion_times_N_per_m_s\":"
                << transport.reduced_energy_diffusion_N_per_m_s
                << ",\"tail_ratio\":"
                << transport.high_energy_tail_ratio << '}';
    std::cout << "}\n";
    return 0;
  }
  catch (const std::exception & e)
  {
    std::cerr << "BOLTZMANN_CANDIDATE_PREFLIGHT_HOLD: " << e.what() << '\n';
    return 2;
  }
}
