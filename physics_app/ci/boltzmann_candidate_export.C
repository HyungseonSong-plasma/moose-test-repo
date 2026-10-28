// Experimental developer-only runner: imported BOLSIG-format data -> one
// candidate EEPF/rate JSON. No MOOSE app objects, no third-party data bundled.
// Actual source hash/rights must be verified by independent case preflight.
#include "PhysicsBoltzmannCrossSections.h"

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
          "emax_eV CELLS species=fraction [species=fraction ...] [--enable-superelastic]");

    const std::string source_path = argv[1], source_sha = argv[2];
    requireSourceHash(source_sha);
    const double EN = parseNumber(argv[3]);
    const double Tg = parseNumber(argv[4]);
    const double emax = parseNumber(argv[5]);
    const auto cells = parseCells(argv[6]);

    std::map<std::string, double> fraction;
    bool enable_superelastic = false;
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
      const auto pos = pair.find('=');
      if (pos == std::string::npos || pos == 0 || pos + 1 >= pair.size())
        throw std::invalid_argument("gas composition requires species=fraction");
      const auto species = pair.substr(0, pos);
      if (!fraction.emplace(species, parseNumber(pair.substr(pos + 1))).second)
        throw std::invalid_argument("duplicate target fraction");
    }
    if (!std::isfinite(EN) || EN < 0 || !(Tg > 0) || !(emax > 0))
      throw std::invalid_argument("invalid gas temperature, energy ceiling or E/N");

    std::ifstream stream(source_path);
    if (!stream.good())
      throw std::invalid_argument("cannot open collision source file");
    auto file = parseBolsigCrossSections(stream);
    auto input = prepareElasticExcitation(file, fraction, emax, enable_superelastic);

    ElasticInput conditions;
    conditions.cells = cells;
    conditions.max_energy_eV = emax;
    conditions.gas_temperature_K = Tg;
    conditions.reduced_field_Td = EN;
    conditions.targets = std::move(input.targets);
    const auto result = solveExcitationSteadyState(
        conditions, input.channels, ExcitationLinearMethod::Auto);
    if (result.maximum_normalized_equation_residual > 1e-8 ||
        result.maximum_collision_number_balance_error > 1e-9)
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
    std::cout << "},\"model\":\"" << (enable_superelastic ?
                  "elastic_excitation_superelastic_steady_dc" :
                  "elastic_excitation_steady_dc") << "\","
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
      std::cout << result.distribution.eepf_eV_minus_3_halves[i];
    }
    std::cout << "],\"mean_energy_eV\":" << result.distribution.mean_energy_eV
              << ",\"rates_m3_per_s\":{";
    for (std::size_t i = 0; i < input.channels.size(); ++i)
    {
      if (i) std::cout << ',';
      escapeJsonString(std::cout, input.channels[i].name);
      std::cout << ':' << result.rate_coefficients_m3_per_s[i];
      if (!input.channels[i].upper_state_target_name.empty())
      {
        std::cout << ',';
        escapeJsonString(std::cout, input.channels[i].upper_state_target_name +
                                    ":superelastic:" + std::to_string(i + 1));
        std::cout << ':' << result.superelastic_rate_coefficients_m3_per_s[i];
      }
    }
    std::cout << "}}\n";
    return 0;
  }
  catch (const std::exception & e)
  {
    std::cerr << "BOLTZMANN_CANDIDATE_PREFLIGHT_HOLD: " << e.what() << '\n';
    return 2;
  }
}
