#include "Chemistry.h"
#include "DDContinuityEq.h"
#include "ActionWarehouse.h"
#include "SCCMInletFlow.h"
#include "IdealGasMixtureState.h"
#include "FEProblemBase.h"

#include "nlohmann/json.hpp"

#include <algorithm>
#include <cmath>
#include <iterator>
#include <iomanip>
#include <map>
#include <fstream>
#include <filesystem>
#include <limits>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>

namespace Plasma
{
namespace
{
using Json = nlohmann::json;
using Coefficients = std::map<std::string, int>;

[[noreturn]] void
fail(const std::string & file, const std::string & detail)
{
  throw std::runtime_error("Plasma mechanism '" + file + "': " + detail);
}

// Single naming contract for every channel: EI-2069 -> R_EI2069,
// EI-02 -> R_EI02, H25 -> R_H25. Never accept a JSON progress override.
std::string
progressFromReactionId(const std::string & id, const std::string & file)
{
  static const std::regex electron_impact(R"(^EI-([0-9]+)$)");
  static const std::regex heavy(R"(^H([0-9]+)$)");
  std::smatch match;
  if (std::regex_match(id, match, electron_impact))
    return "R_EI" + match[1].str();
  if (std::regex_match(id, match, heavy))
    return "R_H" + match[1].str();
  fail(file, "unsupported reaction ID for automatic progress naming: " + id);
}

Coefficients
readCoefficients(const Json & data, const std::string & file)
{
  if (!data.is_object())
    fail(file, "reactants/products must be objects");
  Coefficients result;
  for (auto it = data.begin(); it != data.end(); ++it)
  {
    if (!it.value().is_number_integer())
      fail(file, "noninteger stoichiometry for " + it.key());
    const auto number = it.value().get<int>();
    if (number <= 0)
      fail(file, "nonpositive stoichiometry for " + it.key());
    result.emplace(it.key(), number);
  }
  return result;
}

Coefficients
parseSide(const std::string & text, const std::string & file)
{
  Coefficients parsed;
  const std::regex term(R"(^\s*(?:([1-9][0-9]*)\s*)?([A-Za-z][A-Za-z0-9_]*)\s*$)");
  std::size_t start = 0;
  while (start <= text.size())
  {
    const auto plus = text.find('+', start);
    const auto word = text.substr(start, plus == std::string::npos ? plus : plus - start);
    std::smatch match;
    if (!std::regex_match(word, match, term))
      fail(file, "invalid chemical equation term: " + word);
    const int coefficient = match[1].matched ? std::stoi(match[1].str()) : 1;
    parsed[match[2].str()] += coefficient;
    if (plus == std::string::npos)
      break;
    start = plus + 1;
  }
  return parsed;
}

void
validateReaction(const ReactionRecord & reaction,
                 const std::map<std::string, SpeciesRecord> & species,
                 const std::string & file)
{
  const auto arrow = reaction.equation.find("->");
  if (arrow == std::string::npos ||
      reaction.equation.find("->", arrow + 2) != std::string::npos)
    fail(file, reaction.id + ": equation must contain exactly one '->'");
  if (parseSide(reaction.equation.substr(0, arrow), file) != reaction.reactants ||
      parseSide(reaction.equation.substr(arrow + 2), file) != reaction.products)
    fail(file, reaction.id + ": equation text and structured stoichiometry differ");

  std::map<std::string, long long> element_balance;
  long long charge_balance = 0;
  auto accumulate = [&](const Coefficients & side, int sign)
  {
    for (const auto & [id, count] : side)
    {
      const auto species_it = species.find(id);
      if (species_it == species.end())
        fail(file, reaction.id + ": unknown species " + id);
      charge_balance += static_cast<long long>(sign) * count *
                        species_it->second.charge_number;
      for (const auto & [element, atoms] : species_it->second.elements)
        element_balance[element] += static_cast<long long>(sign) * count * atoms;
    }
  };
  accumulate(reaction.reactants, -1);
  accumulate(reaction.products, 1);
  // Surface charge may be balanced by the wall current. Volume reactions
  // conserve charge entirely within the plasma chemistry catalogue.
  if (reaction.domain == "volume" && charge_balance != 0)
    fail(file, reaction.id + ": charge conservation failed");
  for (const auto & [element, balance] : element_balance)
    if (balance != 0)
      fail(file, reaction.id + ": elemental balance failed for " + element);
}


// Transport table paths belong to the JSON that declares them, not to .i files.
// Absolute paths remain absolute; relative paths are anchored at the JSON parent.
std::string
resolveDataFile(const std::string & filename, const std::string & json_file)
{
  if (filename.empty())
    fail(json_file, "empty transport table filename");
  const auto path = std::filesystem::path(filename);
  const auto resolved = path.is_absolute()
                          ? path.lexically_normal()
                          : (std::filesystem::absolute(json_file).parent_path() / path)
                                .lexically_normal();
  std::ifstream stream(resolved);
  if (!stream)
    fail(json_file, "transport table cannot be opened: " + resolved.string());
  return resolved.string();
}

std::string
requiredText(const Json & object, const char * key, const std::string & file)
{
  if (!object.contains(key) || !object.at(key).is_string() ||
      object.at(key).get<std::string>().empty())
    fail(file, std::string("transport configuration requires nonempty ") + key);
  return object.at(key).get<std::string>();
}

std::vector<std::string>
requiredTextList(const Json & object, const char * key, const std::string & file)
{
  if (!object.contains(key) || !object.at(key).is_array() ||
      object.at(key).empty())
    fail(file, std::string("transport configuration requires nonempty ") + key);
  std::vector<std::string> values;
  for (const auto & item : object.at(key))
  {
    if (!item.is_string() || item.get<std::string>().empty())
      fail(file, std::string("invalid transport list entry for ") + key);
    values.push_back(item.get<std::string>());
  }
  return values;
}

DDTransportRecord
parseDDTransport(const Json & value, const std::string & file, const std::string & id)
{
  if (!value.is_object())
    fail(file, "drift_diffusion transport entry must be an object");
  DDTransportRecord result;
  if (value.at("transport_coef").is_object())
  {
    // Final run schema: uniform typed transport object per species. All
    // Functor names are determined by species ID; gas state is root-owned.
    const auto & entry = value.at("transport_coef");
    const std::set<std::string> keys = {
        "type", "file", "unit", "bounds_policy", "mobility", "diffusivity"};
    for (auto it = entry.begin(); it != entry.end(); ++it)
      if (!keys.count(it.key()))
        fail(file, "species." + id + ".transport_coef unknown option " + it.key());
    const auto model = requiredText(entry, "type", file);
    const auto filename = requiredText(entry, "file", file);
    const auto unit = requiredText(entry, "unit", file);
    for (const auto * retired : {"mobility", "diffusivity", "table_file", "table_units",
                                 "pressure", "gas_temperature", "bounds_policy",
                                 "mobility_source", "diffusivity_source"})
      if (value.contains(retired))
        fail(file, "species." + id + " flat " + retired +
                       " is retired with object-shaped transport_coef");
    result.model = model;
    if (model == "none")
    {
      if (filename != "none" || unit != "none" || entry.size() != 3)
        fail(file, "transport_coef type none requires file=none, unit=none only");
    }
    else if (model == "functor")
    {
      if (filename != "none" || unit != "physical" || entry.size() != 3)
        fail(file, "Functor transport requires file=none and unit=physical; "
                   "reduced coefficient conversion is not implemented for Functor mode");
      result.mobility_source = id + "_mobility";
      result.diffusivity_source = id + "_diffusivity";
    }
    else if (model == "lookup")
    {
      if (entry.contains("mobility") || entry.contains("diffusivity") ||
          (unit != "reduced" && unit != "physical") || filename == "none")
        fail(file, "lookup transport needs a real file and unit=reduced|physical");
      result.table_file = resolveDataFile(filename, file);
      result.table_units = unit;
      if (entry.contains("bounds_policy"))
        result.bounds_policy = requiredText(entry, "bounds_policy", file);
      if (result.bounds_policy != "error" && result.bounds_policy != "clamp")
        fail(file, "lookup bounds_policy must be error or clamp");
      // Reduced transport tables use LIVE root pressure (FV state when solved)
      // and the [Plasmas] temperature Functor; never a species-level alias.
      result.root_owned_gas = unit == "reduced";
      result.pressure = "pressure";
      result.gas_temperature = "temperature";
    }
    else if (model == "constant")
    {
      if (filename != "none" || unit != "physical" ||
          !entry.contains("mobility") || !entry.contains("diffusivity") ||
          entry.size() != 5 || !entry.at("mobility").is_number() ||
          !entry.at("diffusivity").is_number())
        fail(file, "constant transport requires file=none, unit=physical and numeric mobility/diffusivity");
      result.mobility = entry.at("mobility").get<double>();
      result.diffusivity = entry.at("diffusivity").get<double>();
      if (!std::isfinite(result.mobility) || !std::isfinite(result.diffusivity) ||
          result.mobility < 0.0 || result.diffusivity < 0.0)
        fail(file, "constant transport mobility/diffusivity must be finite and nonnegative");
    }
    else
      fail(file, "transport_coef.type must be none, lookup, functor or constant");
    return result;
  }
  // Backward-compatible legacy reader for preserved historical fixtures and
  // Hybrid runs. Canonical new-only JSON must use the typed object above.
  result.model = requiredText(value, "transport_coef", file);
  if (result.model == "constant")
  {
    if (!value.contains("mobility") || !value.at("mobility").is_number() ||
        !value.contains("diffusivity") || !value.at("diffusivity").is_number())
      fail(file, "constant transport requires mobility and diffusivity");
    result.mobility = value.at("mobility").get<double>();
    result.diffusivity = value.at("diffusivity").get<double>();
    if (!std::isfinite(result.mobility) || !std::isfinite(result.diffusivity) ||
        result.mobility < 0.0 || result.diffusivity < 0.0)
      fail(file, "constant mobility/diffusivity must be finite and nonnegative");
    for (const auto * excluded : {"table_file", "coordinate", "mean_energy", "table_units",
                                   "pressure", "gas_temperature", "bounds_policy",
                                   "mobility_source", "diffusivity_source"})
      if (value.contains(excluded))
        fail(file, std::string("constant transport forbids ") + excluded);
  }
  else if (result.model == "functor")
  {
    // Upstream AD coefficient Functor names; numeric values require constant mode.
    result.mobility_source = requiredText(value, "mobility", file);
    result.diffusivity_source = requiredText(value, "diffusivity", file);
    for (const auto * excluded : {"table_file", "table_units", "pressure",
                                   "gas_temperature", "bounds_policy",
                                   "coordinate", "mean_energy",
                                   "mobility_source", "diffusivity_source"})
      if (value.contains(excluded))
        fail(file, std::string("functor transport forbids ") + excluded);
  }
  else if (result.model == "lookup")
  {
    if (value.contains("mobility") || value.contains("diffusivity") ||
        value.contains("mobility_source") || value.contains("diffusivity_source"))
      fail(file, "lookup transport forbids constant or Functor coefficient inputs");
    result.table_file = resolveDataFile(requiredText(value, "table_file", file), file);
    // Lookup always uses the canonical solved electron mean-energy Functor:
    // e_energy_eV. The JSON schema must not expose its coordinate name.
    if (value.contains("coordinate") || value.contains("mean_energy"))
      fail(file, "DD lookup coordinate is implicit: e_energy_eV; do not specify coordinate.");
    result.table_units = requiredText(value, "table_units", file);
    if (result.table_units != "reduced" && result.table_units != "physical")
      fail(file, "lookup table_units must be 'reduced' or 'physical'");
    if (value.contains("bounds_policy"))
      result.bounds_policy = requiredText(value, "bounds_policy", file);
    if (result.bounds_policy != "error" && result.bounds_policy != "clamp")
      fail(file, "bounds_policy must be 'error' or 'clamp'");
    if (result.table_units == "reduced")
    {
      result.pressure = requiredText(value, "pressure", file);
      result.gas_temperature = requiredText(value, "gas_temperature", file);
    }
    else if (value.contains("pressure") || value.contains("gas_temperature"))
      fail(file, "physical transport does not accept reduced-table density inputs");
  }
  else
    fail(file, "transport model must be 'lookup', 'constant' or 'functor'");
  return result;
}

NVTransportRecord
parseNVTransport(const Json & value, const std::string & file)
{
  if (!value.is_object())
    fail(file, "navier_stokes transport entry must be an object");
  NVTransportRecord result;
  result.transport_data_file =
      resolveDataFile(requiredText(value, "transport_data_file", file), file);
  result.temperature = requiredText(value, "temperature", file);
  result.pressure = requiredText(value, "pressure", file);
  result.species = requiredTextList(value, "species", file);
  result.mass_fractions = requiredTextList(value, "mass_fractions", file);
  if (result.species.size() < 2 ||
      result.species.size() != result.mass_fractions.size())
    fail(file, "navier_stokes requires >=2 species and matching mass_fractions");
  if (value.contains("electron_temperature"))
    result.electron_temperature = requiredText(value, "electron_temperature", file);
  if (value.contains("electron_number_density"))
    result.electron_number_density = requiredText(value, "electron_number_density", file);
  if (result.electron_temperature.empty() != result.electron_number_density.empty())
    fail(file, "charged NavierStokes collision inputs need both electron fields");
  return result;
}

// Strict opt-in Poisson schema. S6 geometry is explicit, never inferred from
// transient assembled Mesh/BC state. Legacy multi-file mechanisms are untouched.
PoissonRecord
parsePoissonRecord(const Json & root, const std::string & file)
{
  const std::set<std::string> allowed_root = {
      "species", "equations", "reactions", "ion_surface_current",
      "drift_diffusion_boundaries", "poisson"};
  if (root.size() != allowed_root.size())
    fail(file, "POISSON_ROOT_KEYS_INVALID");
  for (auto it = root.begin(); it != root.end(); ++it)
    if (!allowed_root.count(it.key()))
      fail(file, "POISSON_ROOT_KEYS_INVALID: " + it.key());

  const auto & poisson = root.at("poisson");
  if (!poisson.is_object() || poisson.size() != 2 ||
      !poisson.contains("relative_permittivity") || !poisson.contains("boundaries"))
    fail(file, "POISSON_FIELDS_INVALID");
  const auto & eps = poisson.at("relative_permittivity");
  // The first New-only S6 Poisson cutover is an exact Native parity gate,
  // not a parameter sweep. Reject changed epsilon values in the runtime
  // parser too, rather than relying solely on the Python P0 checker.
  const std::map<std::string, double> expected_eps = {
      {"plasma", 1.0}, {"cover", 3.6}, {"wafer", 12.5},
      {"focus_ring", 8.0}, {"vacuum", 1.0},
      {"coil1", 1.0}, {"coil2", 1.0}, {"coil3", 1.0}};
  std::set<std::string> expected_blocks;
  for (const auto & [block, value] : expected_eps)
  {
    (void)value;
    expected_blocks.insert(block);
  }
  if (!eps.is_object() || eps.size() != expected_blocks.size())
    fail(file, "POISSON_EPS_BLOCKS_INVALID");

  PoissonRecord result;
  for (auto it = eps.begin(); it != eps.end(); ++it)
  {
    if (!expected_blocks.count(it.key()))
      fail(file, "POISSON_EPS_BLOCKS_INVALID: " + it.key());
    if (!it.value().is_number())
      fail(file, "POISSON_EPS_VALUE_INVALID: " + it.key());
    const auto value = it.value().get<double>();
    if (!std::isfinite(value) || value <= 0.0 ||
        value != expected_eps.at(it.key()))
      fail(file, "POISSON_EPS_VALUE_INVALID: " + it.key());
    result.relative_permittivity.emplace(it.key(), value);
  }
  const auto & boundaries = poisson.at("boundaries");
  if (!boundaries.is_object() || boundaries.size() != 2 ||
      !boundaries.contains("ground") || !boundaries.contains("surface_charge"))
    fail(file, "POISSON_BOUNDARY_FIELDS_INVALID");

  const std::set<std::string> expected_ground = {
      "inlet", "outlet", "plasma_electrode", "plasma_metal", "plasma_right",
      "cover_outer_right", "wafer_electrode", "focus_ring_ground",
      "vacuum_outer_ground", "cover_coil_ground", "vacuum_coil_ground"};
  const auto & ground = boundaries.at("ground");
  if (!ground.is_array() || ground.size() != expected_ground.size())
    fail(file, "POISSON_GROUND_BOUNDARIES_INVALID");
  std::set<std::string> unique_ground;
  for (const auto & item : ground)
  {
    if (!item.is_string())
      fail(file, "POISSON_GROUND_BOUNDARIES_INVALID");
    const auto name = item.get<std::string>();
    if (!expected_ground.count(name) || !unique_ground.insert(name).second)
      fail(file, "POISSON_GROUND_BOUNDARIES_INVALID: " + name);
    result.ground_boundaries.push_back(name);
  }

  const auto & surface = boundaries.at("surface_charge");
  const std::map<std::string, std::string> expected_surface = {
      {"plasma_cover", "sigma_s"}, {"plasma_wafer", "sigma_wafer"},
      {"plasma_focus_ring", "sigma_focus_ring"}};
  if (!surface.is_object() || surface.size() != expected_surface.size())
    fail(file, "POISSON_SURFACE_CHARGE_INVALID");
  for (auto it = surface.begin(); it != surface.end(); ++it)
  {
    const auto expected = expected_surface.find(it.key());
    if (expected == expected_surface.end() || !it.value().is_string() ||
        it.value().get<std::string>() != expected->second)
      fail(file, "POISSON_SURFACE_CHARGE_INVALID: " + it.key());
    result.surface_charge.emplace(it.key(), expected->second);
  }

  // The JSON species charge numbers are authoritative for the future G3
  // producer; G1 records them without inventing any charge/source Functor.
  for (const auto & [id, charge] :
       std::map<std::string, int>{{"e", -1}, {"O2p", 1}, {"Om", -1}, {"Op", 1}})
  {
    const auto & species = root.at("species");
    if (!species.contains(id) || !species.at(id).is_object() ||
        !species.at(id).contains("charge_number") ||
        !species.at(id).at("charge_number").is_number_integer() ||
        species.at(id).at("charge_number").get<int>() != charge)
      fail(file, "POISSON_CHARGED_SPECIES_SIGNS_INVALID: " + id);
  }
  return result;
}

// nlohmann::json normally silently keeps the last duplicate key; reject that
// ambiguity for the opt-in single New-only JSON without changing legacy parse.
void
verifyUniquePoissonJsonKeys(const std::string & file)
{
  std::ifstream stream(file);
  if (!stream)
    fail(file, "POISSON_JSON_UNAVAILABLE");
  std::vector<std::set<std::string>> object_keys;
  const auto callback = [&object_keys, &file](int, Json::parse_event_t event, Json & parsed) {
    if (event == Json::parse_event_t::object_start)
      object_keys.emplace_back();
    else if (event == Json::parse_event_t::key)
    {
      const auto name = parsed.get<std::string>();
      if (object_keys.empty() || !object_keys.back().insert(name).second)
        fail(file, "POISSON_JSON_DUPLICATE_KEY: " + name);
    }
    else if (event == Json::parse_event_t::object_end)
      object_keys.pop_back();
    return true;
  };
  (void)Json::parse(stream, callback);
}

} // namespace

bool
DDTransportRecord::equals(const DDTransportRecord & rhs) const
{
  return model == rhs.model && mobility == rhs.mobility && diffusivity == rhs.diffusivity &&
         mobility_source == rhs.mobility_source &&
         diffusivity_source == rhs.diffusivity_source &&
         table_file == rhs.table_file &&
         table_units == rhs.table_units && pressure == rhs.pressure &&
         gas_temperature == rhs.gas_temperature && bounds_policy == rhs.bounds_policy &&
         root_owned_gas == rhs.root_owned_gas;
}

bool
NVTransportRecord::equals(const NVTransportRecord & rhs) const
{
  return transport_data_file == rhs.transport_data_file && temperature == rhs.temperature &&
         pressure == rhs.pressure && electron_temperature == rhs.electron_temperature &&
         electron_number_density == rhs.electron_number_density &&
         species == rhs.species && mass_fractions == rhs.mass_fractions;
}

int
ReactionRecord::net(const std::string & species) const
{
  const auto product = products.find(species);
  const auto reactant = reactants.find(species);
  return (product == products.end() ? 0 : product->second) -
         (reactant == reactants.end() ? 0 : reactant->second);
}

ChemistryData::ChemistryData(const std::vector<std::string> & files)
{
  std::set<std::string> reaction_ids;
  std::set<std::string> progresses;
  for (const auto & file : files)
  {
    std::ifstream input(file);
    if (!input)
      fail(file, "cannot open file");
    Json root;
    try
    {
      input >> root;
    }
    catch (const std::exception & exception)
    {
      fail(file, std::string("invalid JSON: ") + exception.what());
    }
    // FV drift exclusions are derived from the selected species' BC catalogue.
    // Do not admit a separate JSON override that can silently diverge.
    if (root.is_object() && root.contains("boundaries_to_avoid"))
      fail(file, "boundaries_to_avoid is derived from JSON boundaries; remove the duplicate field");
    if (root.is_object() &&
        (root.contains("migration_smoothing_width") ||
         root.contains("wall_migration_gate_smoothing_width")))
      fail(file, "migration_smoothing_width is MOOSE [Continuity]-only, not JSON");
    if (!root.is_object() || !root.contains("species") ||
        !root.contains("equations") || !root.contains("reactions") ||
        !root["species"].is_object() || !root["equations"].is_object() ||
        !root["reactions"].is_array())
      fail(file, "expected species object, equations object and reactions array");

    if (root.contains("poisson"))
    {
      if (files.size() != 1)
        fail(file, "POISSON_REQUIRES_SINGLE_UNIFIED_JSON");
      verifyUniquePoissonJsonKeys(file);
      _poisson = parsePoissonRecord(root, file);
    }

    for (auto it = root["species"].begin(); it != root["species"].end(); ++it)
    {
      const auto & record = it.value();
      if (!record.is_object() || !record.contains("elements") ||
          !record["elements"].is_object() || !record.contains("charge_number") ||
          !record["charge_number"].is_number_integer())
        fail(file, "species '" + it.key() + "' requires elements and integer charge_number");
      if (record.contains("boundaries_to_avoid"))
        fail(file, "species." + it.key() +
                       ".boundaries_to_avoid is unsupported; use the boundaries BC catalogue");
      SpeciesRecord species;
      species.charge_number = record["charge_number"].get<int>();
      for (auto atom = record["elements"].begin(); atom != record["elements"].end(); ++atom)
      {
        if (atom.key().empty() || !atom.value().is_number_integer() ||
            atom.value().get<int>() <= 0)
          fail(file, "invalid elemental composition for " + it.key());
        species.elements[atom.key()] = atom.value().get<int>();
      }
      if (it.key() == "e" && (species.charge_number != -1 || !species.elements.empty()))
        fail(file, "electron 'e' must carry -1 charge and zero nuclei");
      // Versionless, opt-in final-run schema. These fields have the SAME
      // shape for electrons, ions and neutrals; null temperature/density means
      // no separately specified initial solver condition. A charged heavy
      // species with transport enabled obtains a Wall Material; its common
      // gradient method belongs exclusively in [Plasmas].
      const bool new_species_schema =
          record.contains("molar_mass") || record.contains("temperature_eV") ||
          record.contains("sticking_coefficient") ||
          (record.contains("transport_coef") && record.at("transport_coef").is_object());
      if (new_species_schema)
      {
        if (record.contains("wall_use_element_gradient_for_potential"))
          fail(file, "species." + it.key() +
                         ".wall_use_element_gradient_for_potential moved to [Plasmas] wall_gradient");
        for (const auto * key : {"molar_mass", "temperature_eV", "sticking_coefficient",
                                 "transport_coef", "initial_number_density"})
          if (!record.contains(key))
            fail(file, "species." + it.key() + " missing common field " + key);
        if (!record.at("molar_mass").is_number() ||
            !record.at("sticking_coefficient").is_number())
          fail(file, "species." + it.key() + " requires numeric mass and sticking");
        species.molar_mass = record.at("molar_mass").get<double>();
        species.sticking_coefficient = record.at("sticking_coefficient").get<double>();
        if (!std::isfinite(species.molar_mass) || species.molar_mass <= 0.0 ||
            !std::isfinite(species.sticking_coefficient) ||
            species.sticking_coefficient < 0.0 || species.sticking_coefficient > 1.0)
          fail(file, "species." + it.key() + " has invalid molar_mass or sticking_coefficient");
        if (!record.at("temperature_eV").is_null())
        {
          if (!record.at("temperature_eV").is_number())
            fail(file, "species." + it.key() + " temperature_eV must be numeric or null");
          const Real temperature = record.at("temperature_eV").get<double>();
          if (!std::isfinite(temperature) || temperature < 0.0)
            fail(file, "species." + it.key() + " temperature_eV must be finite and nonnegative");
          species.temperature_eV = temperature;
        }
        const auto & transport = record.at("transport_coef");
        if (it.key() != "e" && species.charge_number != 0 &&
            transport.is_object() && transport.value("type", std::string()) != "none")
        {
          IonWallRecord wall;
          wall.molar_mass = species.molar_mass;
          wall.sticking = species.sticking_coefficient;
          wall.ion_temperature_eV = species.temperature_eV.value_or(0.0);
          species.ion_wall = wall;
        }
      }
      // A continuity species' initial particle number density is JSON-owned,
      // independent of heavy-gas mass fractions and energy-density ICs.
      if (record.contains("initial_number_density") &&
          !(new_species_schema && record.at("initial_number_density").is_null()))
      {
        if (!record.at("initial_number_density").is_number())
          fail(file, "initial_number_density must be numeric for " + it.key());
        const double density = record.at("initial_number_density").get<double>();
        if (!std::isfinite(density) || density <= 0.0)
          fail(file, "initial_number_density must be finite and strictly positive [1/m^3] for " +
                     it.key());
        species.initial_number_density = density;
      }
      // Every DD coefficient owner lives in the species JSON record.
      if (record.contains("transport_coef"))
      {
        const auto transport = parseDDTransport(record, file, it.key());
        if (transport.model == "none")
        {
          if (_dd_transport.count(it.key()))
            fail(file, "conflicting none transport with an existing selected DD owner: " + it.key());
        }
        else
        {
          const auto previous = _dd_transport.find(it.key());
          if (previous == _dd_transport.end())
            _dd_transport.emplace(it.key(), transport);
          else if (!previous->second.equals(transport))
          fail(file, "conflicting species transport_coef owner for " + it.key());
        }
      }
      else
        for (const auto * key : {"mobility", "diffusivity", "table_file",
                                  "table_units", "pressure", "gas_temperature",
                                  "bounds_policy", "mobility_source",
                                  "diffusivity_source"})
          if (record.contains(key))
            fail(file, "species '" + it.key() + "' has " + key +
                           " without transport_coef");
      if (record.contains("energy_transport_coef"))
      {
        if (new_species_schema)
          fail(file, "species." + it.key() +
                         ".energy_transport_coef is MOOSE [Energy] transport_coefficient-only");
        // Read-only compatibility for historical flat Hybrid JSON.
        if (it.key() != "e" || !record.at("energy_transport_coef").is_string() ||
            record.at("energy_transport_coef").get<std::string>() != "fluid")
          fail(file, "legacy energy_transport_coef supports only species.e = fluid");
        _fluid_electron_energy_transport = true;
      }
      if (record.contains("molar_mass_kg_mol"))
      {
        if (!record.at("molar_mass_kg_mol").is_number())
          fail(file, "non-numeric molar_mass_kg_mol for " + it.key());
        species.molar_mass_kg_mol = record.at("molar_mass_kg_mol").get<double>();
        if (!std::isfinite(species.molar_mass_kg_mol) || species.molar_mass_kg_mol <= 0.0)
          fail(file, "molar_mass_kg_mol must be finite and positive for " + it.key());
      }
      // Flat species.wall_* keys own ONLY wall-law parameters. Continuous
      // ion state, mobility, potential, temperature and block have their own
      // single owners and must not be duplicated in a wall JSON object.
      if (record.contains("ion_wall"))
        fail(file, "species." + it.key() +
                       ".ion_wall is retired; move wall_* fields to species");
      if (record.contains("wall_migration_gate_smoothing_width") ||
          record.contains("migration_smoothing_width"))
        fail(file, "species." + it.key() +
                       ".migration_smoothing_width is MOOSE [Continuity]-only; "
                       "retired wall_migration_gate_smoothing_width is also forbidden in JSON");
      const std::set<std::string> wall_keys = {
          "wall_molar_mass", "wall_sticking", "wall_ion_temperature_eV",
          "wall_use_element_gradient_for_potential"};
      bool wall_requested = false;
      for (const auto & key : wall_keys)
        wall_requested = wall_requested ||
            (record.contains(key) && (!new_species_schema ||
               key != "wall_use_element_gradient_for_potential"));
      if (wall_requested)
      {
        if (new_species_schema)
          fail(file, "species." + it.key() + " cannot mix retired wall_* physical fields with common species metadata");
        for (const auto & key : wall_keys)
          if (!record.contains(key))
            fail(file, "species." + it.key() + " missing flat wall parameter " + key);
        if (it.key() == "e" || species.charge_number == 0)
          fail(file, "flat wall_* parameters require a charged heavy ion: " + it.key());

        IonWallRecord parsed;
        const auto number = [&](const char * key) {
          if (!record.at(key).is_number())
            fail(file, "species." + it.key() + " nonnumeric " + key);
          const double value = record.at(key).get<double>();
          if (!std::isfinite(value))
            fail(file, "species." + it.key() + " nonfinite " + key);
          return value;
        };
        parsed.molar_mass = number("wall_molar_mass");
        parsed.sticking = number("wall_sticking");
        parsed.ion_temperature_eV = number("wall_ion_temperature_eV");
        if (parsed.molar_mass <= 0.0 || parsed.sticking < 0.0 ||
            parsed.sticking > 1.0 || parsed.ion_temperature_eV < 0.0)
          fail(file, "species." + it.key() + " nonphysical flat wall_* parameter");
        if (!record.at("wall_use_element_gradient_for_potential").is_boolean())
          fail(file, "species." + it.key() + " wall gradient selection must be boolean");
        parsed.use_element_gradient_for_potential =
            record.at("wall_use_element_gradient_for_potential").get<bool>();
        species.ion_wall = parsed;
      }

      // Volume initial composition and inlet/feed composition are independent.
      // Explicit zero is valid; absent metadata is not interpreted as zero.
      for (const auto * key : {"initial_vol_mass_fraction", "initial_inlet_mass_fraction"})
        if (record.contains(key))
        {
          const auto & value = record.at(key);
          if (!value.is_number())
            fail(file, "non-numeric " + std::string(key) + " for " + it.key());
          const double fraction = value.get<double>();
          if (!std::isfinite(fraction) || fraction < 0.0 || fraction > 1.0)
            fail(file, std::string(key) + " must be finite and within [0,1] for " + it.key());
          if (it.key() == "e")
            fail(file, "electron 'e' cannot declare heavy mass fractions");
          if (species.molar_mass_kg_mol <= 0.0)
            fail(file, "initial mass fractions require molar_mass_kg_mol for " + it.key());
          if (std::string(key) == "initial_vol_mass_fraction")
            species.initial_vol_mass_fraction = fraction;
          else
            species.initial_inlet_mass_fraction = fraction;
        }
      if (species.initial_vol_mass_fraction.has_value() !=
          species.initial_inlet_mass_fraction.has_value())
        fail(file, "species " + it.key() +
             " must declare both initial_vol_mass_fraction and initial_inlet_mass_fraction");
      for (const auto * key : {"mass_fraction_variable", "mass_fraction_functor"})
        if (record.contains(key))
        {
          if (!record.at(key).is_string() || record.at(key).get<std::string>().empty())
            fail(file, "species " + it.key() + " requires nonempty " + key);
          if (it.key() == "e")
            fail(file, "electron 'e' cannot bind a heavy mass-fraction state");
          const std::string source = record.at(key).get<std::string>();
          if (!std::isalpha(static_cast<unsigned char>(source.front())) &&
              source.front() != '_')
            fail(file, "invalid mass-fraction state name for " + it.key());
          for (const unsigned char character : source)
            if (!std::isalnum(character) && character != '_')
              fail(file, "invalid mass-fraction state name for " + it.key());
          if (std::string(key) == "mass_fraction_variable")
            species.mass_fraction_variable = source;
          else
            species.mass_fraction_functor = source;
        }
      if (!species.mass_fraction_variable.empty() &&
          !species.mass_fraction_functor.empty())
        fail(file, "species " + it.key() +
             " must select a solved mass_fraction_variable OR a derived mass_fraction_functor");


      const auto existing = _species.find(it.key());
      if (existing == _species.end())
        _species.emplace(it.key(), species);
      else
      {
        if (existing->second.charge_number != species.charge_number ||
            existing->second.elements != species.elements ||
            (existing->second.molar_mass > 0.0 && species.molar_mass > 0.0 &&
             existing->second.molar_mass != species.molar_mass) ||
            (existing->second.temperature_eV && species.temperature_eV &&
             *existing->second.temperature_eV != *species.temperature_eV) ||
            (existing->second.sticking_coefficient > 0.0 && species.sticking_coefficient > 0.0 &&
             existing->second.sticking_coefficient != species.sticking_coefficient) ||
            (existing->second.initial_number_density &&
             species.initial_number_density &&
             *existing->second.initial_number_density != *species.initial_number_density) ||
            (existing->second.molar_mass_kg_mol > 0.0 &&
             species.molar_mass_kg_mol > 0.0 &&
             existing->second.molar_mass_kg_mol != species.molar_mass_kg_mol) ||
            (existing->second.initial_vol_mass_fraction &&
             species.initial_vol_mass_fraction &&
             *existing->second.initial_vol_mass_fraction != *species.initial_vol_mass_fraction) ||
            (existing->second.initial_inlet_mass_fraction &&
             species.initial_inlet_mass_fraction &&
             *existing->second.initial_inlet_mass_fraction != *species.initial_inlet_mass_fraction) ||
            (!existing->second.mass_fraction_variable.empty() &&
             !species.mass_fraction_variable.empty() &&
             existing->second.mass_fraction_variable != species.mass_fraction_variable) ||
            (!existing->second.mass_fraction_functor.empty() &&
             !species.mass_fraction_functor.empty() &&
             existing->second.mass_fraction_functor != species.mass_fraction_functor) ||
            (!existing->second.mass_fraction_variable.empty() &&
             !species.mass_fraction_functor.empty()) ||
            (!existing->second.mass_fraction_functor.empty() &&
             !species.mass_fraction_variable.empty()))
          fail(file, "conflicting species identity for " + it.key());
        if (species.ion_wall && existing->second.ion_wall)
          fail(file, "duplicate ion_wall owner across JSON files for " + it.key());
        if (!existing->second.ion_wall)
          existing->second.ion_wall = species.ion_wall;
        if (!existing->second.initial_number_density)
          existing->second.initial_number_density = species.initial_number_density;
        if (existing->second.molar_mass == 0.0)
          existing->second.molar_mass = species.molar_mass;
        if (!existing->second.temperature_eV)
          existing->second.temperature_eV = species.temperature_eV;
        if (existing->second.sticking_coefficient == 0.0)
          existing->second.sticking_coefficient = species.sticking_coefficient;
        if (existing->second.molar_mass_kg_mol == 0.0)
          existing->second.molar_mass_kg_mol = species.molar_mass_kg_mol;
        if (!existing->second.initial_vol_mass_fraction)
          existing->second.initial_vol_mass_fraction = species.initial_vol_mass_fraction;
        if (!existing->second.initial_inlet_mass_fraction)
          existing->second.initial_inlet_mass_fraction = species.initial_inlet_mass_fraction;
        if (existing->second.mass_fraction_variable.empty())
          existing->second.mass_fraction_variable = species.mass_fraction_variable;
        if (existing->second.mass_fraction_functor.empty())
          existing->second.mass_fraction_functor = species.mass_fraction_functor;
      }
    }

    if (root.contains("gas_state"))
      fail(file, "top-level gas_state is retired; put initial composition on each species");

    if (root.contains("ion_surface_current"))
    {
      if (!_surface_electron_wall_flux.empty())
        fail(file, "duplicate ion_surface_current owner across JSON files");
      const auto & current = root.at("ion_surface_current");
      if (!current.is_object() || current.size() != 1 ||
          !current.contains("electron_wall_number_flux") ||
          !current.at("electron_wall_number_flux").is_string())
        fail(file, "ion_surface_current requires exactly electron_wall_number_flux");
      _surface_electron_wall_flux = current.at("electron_wall_number_flux").get<std::string>();
      // DDEnergyEq emits the historical name; S6 scratch wall canonicalization
      // can instead emit e_wall_number_flux. The JSON must name its chosen
      // producer explicitly: never guess an alias or create a second electron law.
      if (_surface_electron_wall_flux != "electron_wall_number_flux" &&
          _surface_electron_wall_flux != "e_wall_number_flux")
        fail(file, "ion_surface_current requires an explicit known electron wall Functor");
    }

    // New-only drift_diffusion_boundaries groups operators directly by
    // sidesets. Each BC key identifies its species and operator; the parser
    // derives the solver variable, canonical flux and FV unit/sign factor.
    // Historical "boundaries": {"sides": {"bcs": {...}}} remains supported.
    if (root.contains("drift_diffusion_boundary"))
      fail(file, "drift_diffusion_boundary is retired; use drift_diffusion_boundaries");
    const bool modern_boundaries = root.contains("drift_diffusion_boundaries");
    if (modern_boundaries && root.contains("boundaries"))
      fail(file, "choose one boundary catalogue: drift_diffusion_boundaries or boundaries");

    Json normalized_boundaries = Json::object();
    if (modern_boundaries)
    {
      const auto & groups = root.at("drift_diffusion_boundaries");
      if (!groups.is_object() || groups.empty())
        fail(file, "drift_diffusion_boundaries must be a nonempty object");

      // Physical sidesets are declared ONCE by the enclosing JSON group.
      // A BC name may occur in multiple disjoint groups; merge its sides
      // into one MOOSE BC owner instead of registering duplicate residuals.
      static const std::regex identifier(R"(^[A-Za-z_][A-Za-z_0-9]*$)");
      std::set<std::string> declared_sides;
      std::map<std::string, std::pair<Json, std::set<std::string>>> merged_bcs;
      for (auto group = groups.begin(); group != groups.end(); ++group)
      {
        if (!group.value().is_object() || group.value().empty())
          fail(file, "drift_diffusion_boundaries group must contain direct BC objects: " +
                         group.key());
        std::set<std::string> group_sides;
        std::istringstream sides(group.key());
        for (std::string side; sides >> side;)
          if (!std::regex_match(side, identifier) ||
              !group_sides.insert(side).second ||
              !declared_sides.insert(side).second)
            fail(file, "overlapping or invalid drift_diffusion_boundaries sideset: " + side);
        if (group_sides.empty())
          fail(file, "drift_diffusion_boundaries group has no mesh sidesets");

        for (auto item = group.value().begin(); item != group.value().end(); ++item)
        {
          const auto & spec = item.value();
          if (!std::regex_match(item.key(), identifier) ||
              !spec.is_object() || spec.size() != 1 ||
              !spec.contains("type") || !spec.at("type").is_string())
            fail(file, "drift_diffusion_boundaries BC requires only type: " + item.key());
          const std::string type = spec.at("type").get<std::string>();
          const bool electron_energy = item.key().rfind("e_energy_", 0) == 0;
          const auto separator = item.key().find('_');
          if (separator == std::string::npos)
            fail(file, "BC name requires species prefix: " + item.key());
          const std::string species_id = electron_energy ? "e" : item.key().substr(0, separator);
          if (_species.find(species_id) == _species.end())
            fail(file, "unknown drift-diffusion BC species: " + species_id);
          const bool electron = species_id == "e";
          if (electron != (type == "FEMElectronSheathBC" ||
                           type == "FEMElectronEnergySheathBC") ||
              (electron_energy != (type == "FEMElectronEnergySheathBC")))
            fail(file, "BC species/type mismatch: " + item.key());
          if (!electron && type != "FVFunctorNeumannBC" &&
              type != "FVLogMolarDielectricFluxBC")
            fail(file, "unsupported ion FV BC type: " + item.key());
          if (!electron && _species.at(species_id).charge_number == 0)
            fail(file, "neutral species cannot own ion FV wall BC: " + item.key());

          Json bc = {{"type", type},
                     {"variable", electron_energy ? "log_e_energy" : "log_" + species_id}};
          if (electron)
          {
            bc["wall_number_flux"] = "e_wall_number_flux";
            if (electron_energy)
              bc["mean_energy"] = "e_energy_eV";
          }
          else if (type == "FVFunctorNeumannBC")
          {
            bc["functor"] = species_id + "_wall_number_flux";
            // Convert outward particle flux to inward-signed molar Neumann
            // flux once; the JSON never owns a numerical factor.
            bc["factor"] = -1.0 / 6.02214076e23;
          }
          else
            bc["signed_number_flux"] = species_id + "_wall_number_flux";

          const auto [owner, inserted] = merged_bcs.emplace(
              item.key(), std::make_pair(bc, group_sides));
          if (!inserted)
          {
            if (owner->second.first != bc)
              fail(file, "BC name has conflicting types or species across groups: " + item.key());
            for (const auto & side : group_sides)
              if (!owner->second.second.insert(side).second)
                fail(file, "BC name repeats a physical sideset: " + item.key() + "/" + side);
          }
        }
      }

      // The existing typed BC registry and warehouse guard use one logical
      // owner per unique BC name, while different BCs may share sidesets.
      for (const auto & [name, owner] : merged_bcs)
      {
        std::string joined;
        for (const auto & side : owner.second)
          joined += (joined.empty() ? "" : " ") + side;
        if (!normalized_boundaries.contains(joined))
          normalized_boundaries[joined] = {{"bcs", Json::object()}};
        normalized_boundaries[joined]["bcs"][name] = owner.first;
      }
    }

    if (root.contains("boundaries") || modern_boundaries)
    {
      if (_has_boundaries)
        fail(file, "duplicate boundaries owner across JSON files");
      const auto & catalogue =
          modern_boundaries ? normalized_boundaries : root.at("boundaries");
      if (!catalogue.is_object() || catalogue.empty())
        fail(file, "boundaries must be a nonempty object");

      static const std::regex identifier(R"(^[A-Za-z_][A-Za-z_0-9]*$)");
      std::set<std::string> used_mesh_boundaries;
      std::set<std::string> used_bc_names;
      std::set<std::string> operator_owners;
      for (auto group = catalogue.begin(); group != catalogue.end(); ++group)
      {
        // The JSON object key IS the physical mesh sideset name, e.g.
        // "plasma_wafer". A whitespace-separated key also preserves a
        // historical single BC owning several sidesets, without splitting it.
        const auto & item = group.value();
        if (!item.is_object() || item.size() != 1 ||
            !item.contains("bcs") || !item.at("bcs").is_object())
          fail(file, "boundaries." + group.key() +
                         " requires exactly a bcs object; its key is the mesh boundary");

        BoundaryRecord record;
        std::istringstream input(group.key());
        for (std::string side; input >> side;)
          record.mesh_boundaries.push_back(side);
        if (record.mesh_boundaries.empty())
          fail(file, "empty boundaries mesh sideset key");
        std::set<std::string> local_sides;
        for (const auto & side : record.mesh_boundaries)
          if (!std::regex_match(side, identifier) ||
              !local_sides.insert(side).second ||
              (!modern_boundaries && !used_mesh_boundaries.insert(side).second))
            fail(file, "invalid or duplicate boundaries mesh sideset: " + side);

        for (auto bc = item.at("bcs").begin(); bc != item.at("bcs").end(); ++bc)
        {
          const auto & spec = bc.value();
          if (!std::regex_match(bc.key(), identifier) ||
              !used_bc_names.insert(bc.key()).second)
            fail(file, "invalid or duplicate DriftDiffusion BC name: " + bc.key());
          if (!spec.is_object() || !spec.contains("type") || !spec.contains("variable") ||
              !spec.at("type").is_string() || !spec.at("variable").is_string())
            fail(file, "boundaries BC " + bc.key() + " requires type and variable strings");

          BoundaryBCRecord entry;
          entry.type = spec.at("type").get<std::string>();
          entry.variable = spec.at("variable").get<std::string>();
          const bool particle = entry.type == "FEMElectronSheathBC";
          const bool energy = entry.type == "FEMElectronEnergySheathBC";
          const bool fv_neumann = entry.type == "FVFunctorNeumannBC";
          const bool fv_dielectric = entry.type == "FVLogMolarDielectricFluxBC";
          if (!particle && !energy && !fv_neumann && !fv_dielectric)
            fail(file, "boundaries BC type is not yet supported: " +
                           entry.type + " for " + bc.key());
          if (spec.size() != (energy || fv_neumann ? 4 : 3))
            fail(file, "wrong named arguments in boundaries BC " + bc.key());
          if (particle || energy)
          {
            if (!spec.contains("wall_number_flux") || !spec.at("wall_number_flux").is_string())
              fail(file, "missing FEM wall_number_flux in boundaries BC " + bc.key());
            entry.wall_number_flux = spec.at("wall_number_flux").get<std::string>();
          }
          if (energy)
          {
            if (!spec.contains("mean_energy") || !spec.at("mean_energy").is_string())
              fail(file, "missing mean_energy in boundaries BC " + bc.key());
            entry.mean_energy = spec.at("mean_energy").get<std::string>();
          }
          if (fv_neumann)
          {
            if (!spec.contains("functor") || !spec.at("functor").is_string() ||
                !spec.contains("factor") || !spec.at("factor").is_number())
              fail(file, "FV Neumann BC requires functor and numeric factor: " + bc.key());
            entry.functor = spec.at("functor").get<std::string>();
            entry.factor = spec.at("factor").get<double>();
            constexpr double minus_inv_avogadro = -1.6605390671738466e-24;
            if (!std::isfinite(entry.factor) ||
                std::abs(entry.factor / minus_inv_avogadro - 1.0) > 1.0e-12)
              fail(file, "FV Neumann factor must be -1/N_A: " + bc.key());
          }
          if (fv_dielectric)
          {
            if (!spec.contains("signed_number_flux") ||
                !spec.at("signed_number_flux").is_string())
              fail(file, "FV dielectric BC requires signed_number_flux: " + bc.key());
            entry.signed_number_flux = spec.at("signed_number_flux").get<std::string>();
          }
          if (entry.variable.empty() ||
              ((particle || energy) && entry.wall_number_flux.empty()) ||
              (energy && entry.mean_energy.empty()) ||
              (fv_neumann && entry.functor.empty()) ||
              (fv_dielectric && entry.signed_number_flux.empty()))
            fail(file, "empty parameter value in boundaries BC " + bc.key());

          // Do not double-own a physical residual under two different labels.
          for (const auto & side : record.mesh_boundaries)
          {
            const std::string key = entry.type + "/" + entry.variable + "/" + side;
            if (!operator_owners.insert(key).second)
              fail(file, "duplicate DriftDiffusion BC operator owner: " + key);
          }
          record.bcs.emplace(bc.key(), std::move(entry));
        }
        _boundaries.emplace(group.key(), std::move(record));
      }
      _has_boundaries = true;
    }

    // Drift-diffusion coefficients now live on species; Navier-Stokes stays mixture-owned.
    if (root.contains("transport_coefficients"))
    {
      const auto & coefficients = root.at("transport_coefficients");
      if (!coefficients.is_object())
        fail(file, "transport_coefficients must be an object");
      for (auto it = coefficients.begin(); it != coefficients.end(); ++it)
        if (it.key() != "drift_diffusion" && it.key() != "navier_stokes")
          fail(file, "unknown transport_coefficients section: " + it.key());

      if (coefficients.contains("drift_diffusion"))
        fail(file, "transport_coefficients.drift_diffusion is retired; "
                   "declare transport_coef and mobility/diffusivity in species.<id>");
      if (coefficients.contains("navier_stokes"))
      {
        const auto record = parseNVTransport(coefficients.at("navier_stokes"), file);
        if (!_nv_transport)
          _nv_transport = std::make_unique<NVTransportRecord>(record);
        else if (!_nv_transport->equals(record))
          fail(file, "conflicting navier_stokes transport owner across JSON files");
      }
    }

    std::set<std::string> equation_ids;
    for (auto it = root["equations"].begin(); it != root["equations"].end(); ++it)
    {
      if (!it.value().is_string())
        fail(file, "equation for " + it.key() + " is not a string");
      equation_ids.insert(it.key());
    }

    for (const auto & entry : root["reactions"])
    {
      // The backend contract has exactly one vocabulary for units and loss.
      // Do not silently accept a stale sidecar key or accidentally combine
      // an old signed delta with the new positive-loss RHS projection.
      if (entry.is_object() &&
          (entry.contains("progress_units") || entry.contains("electron_energy_change_eV")))
        fail(file, "legacy reaction keys progress_units/electron_energy_change_eV "
                   "are forbidden; use units and energy_loss_eV.");
      if (!entry.is_object() || !entry.contains("id") || !entry["id"].is_string() ||
          !entry.contains("units") || !entry["units"].is_string() ||
          !entry.contains("reactants") || !entry.contains("products"))
        fail(file, "reaction needs id, units, reactants and products");
      if (entry.contains("progress"))
        fail(file, "progress is derived from reaction ID; remove the JSON progress field");
      ReactionRecord reaction;
      reaction.id = entry["id"].get<std::string>();
      reaction.progress = progressFromReactionId(reaction.id, file);
      if (!reaction_ids.insert(reaction.id).second ||
          !progresses.insert(reaction.progress).second)
        fail(file, "duplicate reaction ID or generated progress owner: " + reaction.id);
      if (!equation_ids.erase(reaction.id))
        fail(file, reaction.id + ": missing equation mapping");
      reaction.equation = root["equations"].at(reaction.id).get<std::string>();
      reaction.reactants = readCoefficients(entry["reactants"], file);
      reaction.products = readCoefficients(entry["products"], file);
      if (entry.contains("domain"))
      {
        if (!entry.at("domain").is_string())
          fail(file, reaction.id + ": domain must be a string");
        reaction.domain = entry.at("domain").get<std::string>();
      }
      if (reaction.domain != "volume" && reaction.domain != "surface")
        fail(file, reaction.id + ": domain must be volume or surface");
      const std::string units = reaction.domain == "surface" ? "mol/(m^2 s)" : "mol/(m^3 s)";
      if (entry.at("units").get<std::string>() != units)
        fail(file, reaction.id + ": progress units must be " + units);

      if (entry.contains("rate"))
      {
        const auto & rate = entry.at("rate");
        if (!rate.is_object() || !rate.contains("model") || !rate.at("model").is_string())
          fail(file, reaction.id + ": rate must contain a model");
        auto & law = reaction.rate;
        law.model = rate.at("model").get<std::string>();
        const bool surface = reaction.domain == "surface";
        if (!surface && law.model != "constant" && law.model != "power_law")
          fail(file, reaction.id + ": unsupported volume rate model");
        if (surface && law.model != "thermal_sticking" &&
            law.model != "deferred_charged_flux")
          fail(file, reaction.id + ": unsupported surface rate model");

        const std::set<std::string> accepted = surface
            ? std::set<std::string>{"model", "sticking"}
            : std::set<std::string>{"model", "A", "basis", "T_ref", "exponent"};
        for (auto it = rate.begin(); it != rate.end(); ++it)
          if (!accepted.count(it.key()))
            fail(file, reaction.id + ": unsupported rate key " + it.key());

        if (surface)
        {
          if (!rate.contains("sticking") || !rate.at("sticking").is_number())
            fail(file, reaction.id + ": surface rate requires sticking");
          law.sticking = rate.at("sticking").get<double>();
          if (!std::isfinite(law.sticking) || law.sticking < 0.0)
            fail(file, reaction.id + ": sticking must be finite and nonnegative");
        }
        else
        {
          if (!rate.contains("A") || !rate.at("A").is_number() ||
              !rate.contains("basis") || !rate.at("basis").is_string())
            fail(file, reaction.id + ": volume rate requires numeric A and basis");
          law.A_input = rate.at("A").get<double>();
          law.basis = rate.at("basis").get<std::string>();
          if (!std::isfinite(law.A_input) || law.A_input < 0.0)
            fail(file, reaction.id + ": A must be finite and nonnegative");
          if (law.basis != "particle" && law.basis != "molar")
            fail(file, reaction.id + ": rate basis must be particle or molar");
          if (law.model == "constant" &&
              (rate.contains("T_ref") || rate.contains("exponent")))
            fail(file, reaction.id + ": constant rate forbids power-law parameters");
          if (law.model == "power_law")
          {
            if (!rate.contains("T_ref") || !rate.contains("exponent") ||
                !rate.at("T_ref").is_number() || !rate.at("exponent").is_number())
              fail(file, reaction.id + ": power_law requires T_ref and exponent");
            law.T_ref = rate.at("T_ref").get<double>();
            law.exponent = rate.at("exponent").get<double>();
            if (!std::isfinite(law.T_ref) || law.T_ref <= 0.0 ||
                !std::isfinite(law.exponent))
              fail(file, reaction.id + ": invalid power-law temperature parameters");
          }
          unsigned int order = 0;
          for (const auto & reactant : reaction.reactants)
            order += reactant.second;
          if (order == 0)
            fail(file, reaction.id + ": rate requires reactants");
          law.A_molar = law.A_input *
              (law.basis == "particle"
                   ? std::pow(6.02214076e23, static_cast<double>(order - 1))
                   : 1.0);
          if (!std::isfinite(law.A_molar))
            fail(file, reaction.id + ": molar rate coefficient overflow");
        }
      }
      else if (reaction.domain == "surface")
        fail(file, reaction.id + ": surface reactions require explicit rate");

      // Executable heavy and surface rate laws must provide physical molar
      // masses for every heavy reactant/product, not silently omit wall flux.
      if (!reaction.rate.model.empty())
      {
        std::set<std::string> involved;
        for (const auto & item : reaction.reactants)
          involved.insert(item.first);
        for (const auto & item : reaction.products)
          involved.insert(item.first);
        for (const auto & species_id : involved)
          if (species_id != "e" &&
              (_species.find(species_id) == _species.end() ||
               _species.at(species_id).molar_mass_kg_mol <= 0.0))
            fail(file, reaction.id + ": missing heavy molar_mass_kg_mol for " + species_id);
      }

      if (!entry.contains("energy_loss_eV"))
        fail(file, reaction.id + ": missing explicit electron energy policy");
      const auto & energy = entry["energy_loss_eV"];
      if (energy.is_number())
      {
        reaction.energy_loss_eV = energy.get<double>();
        if (!std::isfinite(reaction.energy_loss_eV) || reaction.energy_loss_eV < 0.0)
          fail(file, reaction.id + ": electron energy loss must be finite and nonnegative");
        reaction.contributes_electron_energy = reaction.energy_loss_eV != 0.0;
      }
      else if (energy.is_object() && energy.value("model", std::string()) == "functor" &&
               energy.contains("name") && energy["name"].is_string())
      {
        reaction.energy_loss_functor = energy["name"].get<std::string>();
        if (reaction.energy_loss_functor.empty())
          fail(file, reaction.id + ": empty energy-loss functor");
        reaction.contributes_electron_energy = true;
      }
      else if (!(energy.is_object() && energy.value("model", std::string()) == "none"))
        fail(file, reaction.id + ": energy loss needs a nonnegative number, positive-loss functor or model none");
      if (reaction.domain == "surface" && reaction.contributes_electron_energy)
        fail(file, reaction.id + ": surface electron-energy sources are unsupported");
      validateReaction(reaction, _species, file);
      _reactions.push_back(std::move(reaction));
    }
    if (!equation_ids.empty())
      fail(file, "equation without matching reaction ID: " + *equation_ids.begin());
  }
  if (_fluid_electron_energy_transport && _dd_transport.find("e") == _dd_transport.end())
    fail("<merged plasma mechanism>",
         "species.e.energy_transport_coef=fluid requires species.e.transport_coef");
  for (const auto & [id, config] : _dd_transport)
    if (_species.find(id) == _species.end())
      fail("<merged plasma mechanism>", "species transport_coef references unknown species: " + id);
  if (_nv_transport)
    for (const auto & id : _nv_transport->species)
      if (_species.find(id) == _species.end())
        fail("<merged plasma mechanism>", "navier_stokes references unknown species: " + id);
}

bool
ChemistryData::hasIonWalls() const
{
  for (const auto & [id, record] : _species)
    if (record.ion_wall)
      return true;
  return false;
}

const DDTransportRecord *
ChemistryData::ddTransport(const std::string & id) const
{
  const auto it = _dd_transport.find(id);
  return it == _dd_transport.end() ? nullptr : &it->second;
}

const NVTransportRecord *
ChemistryData::nvTransport() const
{
  return _nv_transport.get();
}

const SpeciesRecord &
ChemistryData::species(const std::string & id) const
{
  auto it = _species.find(id);
  if (it == _species.end())
    throw std::runtime_error("Species '" + id + "' is absent from [Plasmas]/files");
  return it->second;
}

bool
ChemistryData::hasSpeciesSource(const std::string & id) const
{
  for (const auto & reaction : _reactions)
    if (reaction.domain == "volume" && reaction.net(id) != 0)
      return true;
  return false;
}

bool
ChemistryData::hasElectronEnergySource() const
{
  for (const auto & reaction : _reactions)
    if (reaction.domain == "volume" && reaction.contributes_electron_energy)
      return true;
  return false;
}

} // namespace Plasma


// Chemistry Physics generates signed source contributions from the validated catalogue.

namespace Plasma
{
namespace
{
struct SourceExpression
{
  std::vector<std::string> names;
  std::vector<std::string> symbols;
  std::vector<std::string> parts;

  std::string expression() const
  {
    std::string result;
    for (const auto & part : parts)
      result += (result.empty() ? "" : "+") + part;
    return result;
  }

  std::string symbol(const std::string & name)
  {
    const auto result = "f" + std::to_string(names.size());
    names.push_back(name);
    symbols.push_back(result);
    return result;
  }
};

std::string
realLiteral(double value)
{
  std::ostringstream stream;
  stream << std::setprecision(17) << value;
  return stream.str();
}

} // namespace

InputParameters
Chemistry::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Generates one source Functor per species and one electron-energy source "
      "from validated [Plasmas]/files reaction channels; kinetic progress remains separately owned.");
  return params;
}

Chemistry::Chemistry(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  if (chemistryData().reactions().empty())
    mooseError("Activated [Transport]/[Chemistry] requires reactions in [Plasmas]/files");
}

void
Chemistry::checkIntegrity() const
{
  // The shared PlasmaMechanism constructor validates all ID <-> equation,
  // elemental and charge conservation, unique rate owners, signed energy
  // changes, and referenced species before any generated source is used.
}

void
Chemistry::addFunctorMaterials()
{
  const auto & mechanism = chemistryData();
  std::map<std::string, SourceExpression> particle;
  SourceExpression energy;

  // The shared mechanism merges reactions from every [Plasmas]/files entry.
  // For each reaction ID, project its independently owned progress R_k onto
  // species production (nu_s,k * R_k) and signed electron energy transfer
  // (delta_epsilon_k * R_k). Even identical equations remain separate channels.
  // After this loop, all electron contributions form ONE Q_e_molar_eV Functor;
  // DDEnergyEq inserts that aggregate as ONE RHS Kernel, not one per reaction.
  for (const auto & reaction : mechanism.reactions())
  {
    // Boundary reactions must not be projected into volumetric RHS kernels.
    if (reaction.domain == "surface")
      continue;
    std::set<std::string> touched;
    for (const auto & [id, coefficient] : reaction.reactants)
      touched.insert(id);
    for (const auto & [id, coefficient] : reaction.products)
      touched.insert(id);

    for (const auto & id : touched)
    {
      const auto coefficient = reaction.net(id);
      if (coefficient == 0)
        continue;
      auto & source = particle[id];
      const auto symbol = source.symbol(reaction.progress);
      source.parts.push_back("(" + std::to_string(coefficient) + ")*" + symbol);
    }

    if (reaction.contributes_electron_energy)
    {
      const auto progress = energy.symbol(reaction.progress);
      if (!reaction.energy_loss_functor.empty())
      {
        // The source Functor is a POSITIVE energy-loss magnitude [eV/event].
        // One negative sign is applied at the aggregate electron RHS only.
        const auto loss = energy.symbol(reaction.energy_loss_functor);
        energy.parts.push_back("(-1.0)*(" + loss + ")*" + progress);
      }
      else
        energy.parts.push_back("(-1.0)*(" + realLiteral(reaction.energy_loss_eV) +
                               ")*" + progress);
    }
  }

  const std::string type = "ADParsedFunctorMaterial";
  for (const auto & [id, source] : particle)
  {
    auto params = getFactory().getValidParams(type);
    params.set<std::string>("property_name") = "S_" + id + "_molar";
    params.set<std::vector<std::string>>("functor_names") = source.names;
    params.set<std::vector<std::string>>("functor_symbols") = source.symbols;
    params.set<std::string>("expression") = source.expression();
    assignBlocks(params, _blocks);
    getProblem().addFunctorMaterial(type, "chemistry_" + id + "_source", params);
  }

  if (!energy.parts.empty())
  {
    auto params = getFactory().getValidParams(type);
    params.set<std::string>("property_name") = "Q_e_molar_eV";
    params.set<std::vector<std::string>>("functor_names") = energy.names;
    params.set<std::vector<std::string>>("functor_symbols") = energy.symbols;
    params.set<std::string>("expression") = energy.expression();
    assignBlocks(params, _blocks);
    getProblem().addFunctorMaterial(type, "chemistry_e_energy_source", params);
  }

  // G3: only opt-in New-only Poisson obtains live charge projections.
  // G5 must retire all three homonymous Native C0 producers before Native P2.
  if (mechanism.poisson())
  {
    const auto add_charge_functor =
        [this](const std::string & property,
               const std::vector<std::string> & functors,
               const std::vector<std::string> & symbols,
               const std::string & expression)
    {
      const std::string type = "ADParsedFunctorMaterial";
      auto params = getFactory().getValidParams(type);
      params.set<std::string>("property_name") = property;
      params.set<std::vector<std::string>>("functor_names") = functors;
      params.set<std::vector<std::string>>("functor_symbols") = symbols;
      params.set<std::string>("expression") = expression;
      assignBlocks(params, _blocks);
      getProblem().addFunctorMaterial(type, "plasma_" + property, params);
    };

    // G1 validates z(O2p)=z(Op)=+1 and z(e)=z(Om)=-1.
    add_charge_functor("charge_number_density",
                       {"O2p_number_density", "Op_number_density",
                        "n_e_physical", "Om_number_density"},
                       {"ni", "nop", "ne", "nm"}, "ni+nop-ne-nm");
    add_charge_functor("charge_density_C_m3",
                       {"charge_number_density"}, {"nq"},
                       "1.602176634e-19*nq");
    add_charge_functor("poisson_source",
                       {"charge_number_density"}, {"nq"},
                       "1.8095128179727827e-08*nq");
  }
}
} // namespace Plasma

using Plasma::Chemistry;
registerPhysicsBaseTasks("PhysicsApp", Chemistry);
registerMooseAction("PhysicsApp", Chemistry, "check_integrity");
registerMooseAction("PhysicsApp", Chemistry, "add_functor_material");

// The [Plasmas] mechanism owner is implemented beside its Chemistry data model.
InputParameters
PlasmasAction::validParams()
{
  InputParameters params = Action::validParams();
  params.addParam<std::vector<FileName>>(
      "files", {}, "Ordered JSON mechanisms shared by Plasma Chemistry and Transport.");
  params.addParam<Real>("pressure", "Initial Navier-Stokes pressure [Pa] when a solved "
                                    "pressure variable exists; otherwise uniform gas pressure.");
  params.addParam<Real>("temperature", "Uniform gas temperature [K]; enables canonical Gas State.");
  params.addParam<MooseEnum>(
      "wall_gradient", MooseEnum("adjacent_element face", "adjacent_element"),
      "Wall electric-field gradient evaluation for all selected FV ion walls: "
      "adjacent_element evaluates the sided element gradient, face evaluates a FaceArg gradient.");
  params.addParam<MooseEnum>("state_model", MooseEnum("ideal_gas", "ideal_gas"),
                             "Canonical mixture equation of state.");
  // Every solved heavy-species mass fraction receives its JSON volume initial
  // condition. Derived/constraint Functors do not own an independent solver IC.
  params.addParam<std::vector<BoundaryName>>(
      "inlet_boundaries", {}, "Named inlet sidesets; never inferred from walls.");
  params.addParam<Real>("sccm",
                        "Positive standard volumetric feed rate [standard cm^3/min]; "
                        "with inlet_area, publishes feed mass flow and speed.");
  params.addParam<Real>("inlet_area",
                        "Required with sccm: user-specified physical inlet area [m^2]. "
                        "Never inferred from sidesets.");
  params.addParam<Real>("standard_molar_volume", 0.0224136,
                        "Reference molar volume [m^3/mol], default historical 0 C / 1 atm.");
  params.addParam<MooseEnum>(
      "inlet_species_bc_ownership", MooseEnum("root_dirichlet external_flux", "root_dirichlet"),
      "root_dirichlet generates composition BCs; external_flux preserves user WCNS "
      "species flux BCs without adding duplicate Dirichlet conditions.");
  return params;
}

PlasmasAction::PlasmasAction(const InputParameters & params)
  : Action(params),
    _data([this]() {
      std::vector<std::string> paths;
      for (const auto & filename : getParam<std::vector<FileName>>("files"))
        paths.emplace_back(filename);
      return paths;
    }())
{
  if (isParamValid("pressure") != isParamValid("temperature"))
    paramError("pressure", "Specify both pressure [Pa] and temperature [K] at [Plasmas].");
  if (gasStateEnabled() &&
      (!std::isfinite(getParam<Real>("pressure")) || getParam<Real>("pressure") <= 0.0 ||
       !std::isfinite(getParam<Real>("temperature")) || getParam<Real>("temperature") <= 0.0))
    paramError("pressure", "Gas pressure and temperature must be finite and strictly positive.");
  if (isParamValid("sccm"))
  {
    const Real feed = getParam<Real>("sccm");
    if (!std::isfinite(feed) || feed <= 0.0)
      paramError("sccm", "SCCM feed rate must be finite and strictly positive.");
    if (getParam<std::vector<BoundaryName>>("inlet_boundaries").empty())
      paramError("inlet_boundaries", "sccm requires explicit inlet sidesets for species Dirichlet BCs.");
    if (!gasStateEnabled())
      paramError("pressure", "sccm inlet composition requires pressure and temperature.");
    if (!isParamValid("inlet_area") || !std::isfinite(getParam<Real>("inlet_area")) ||
        getParam<Real>("inlet_area") <= 0.0)
      paramError("inlet_area", "sccm requires a finite, strictly positive inlet_area [m^2].");
  }
  else
  {
    if (!getParam<std::vector<BoundaryName>>("inlet_boundaries").empty())
      paramError("sccm", "inlet_boundaries requires sccm to activate inlet species Dirichlet BCs.");
    if (isParamValid("inlet_area"))
      paramError("inlet_area", "inlet_area without sccm has no active feed.");
    if (getParam<MooseEnum>("inlet_species_bc_ownership") == "external_flux")
      paramError("inlet_species_bc_ownership", "external_flux requires positive sccm.");
  }
  if (!std::isfinite(getParam<Real>("standard_molar_volume")) ||
      getParam<Real>("standard_molar_volume") <= 0.0)
    paramError("standard_molar_volume",
               "standard_molar_volume must be finite and strictly positive.");
}

void
PlasmasAction::act()
{
  // C2 is an opt-in JSON surface, with NO independent ownership-mode flag.
  // DDContinuityEq.fvm_species is the only discretization selector. Old Native
  // FV Kernel/BC owners must already have been removed from disposable Scratch.
  bool has_ion_fv_bc = false;
  for (const auto & [group, boundary] : _data.boundaries())
    for (const auto & [name, bc] : boundary.bcs)
      has_ion_fv_bc = has_ion_fv_bc ||
          bc.type == "FVFunctorNeumannBC" || bc.type == "FVLogMolarDielectricFluxBC";
  const bool c2_requested = _data.hasIonWalls() ||
      !_data.surfaceElectronWallFlux().empty() || has_ion_fv_bc;

  if (c2_requested)
  {
    const auto continuity = _awh.getActions<Plasma::DDContinuityEq>();
    if (continuity.size() != 1)
      mooseError("C2 requires exactly one DDContinuityEq species-selection owner");
    const auto fvm = continuity.front()->getParam<std::vector<std::string>>("fvm_species");
    const auto & potential = continuity.front()->getParam<VariableName>("fem_potential");
    const std::set<std::string> allowed = {"O2p", "Om", "Op"};
    std::set<std::string> selected, configured;
    for (const auto & id : fvm)
      if (id != "e" && _data.species(id).charge_number != 0)
      {
        if (!allowed.count(id))
          mooseError("C2 has no characterized ion wall contract for selected species ", id);
        // Explicit species identity must agree with the original 3-ion S6
        // charge ledger before using it to sign migration and wall current.
        const int expected_charge = id == "Om" ? -1 : 1;
        if (_data.species(id).charge_number != expected_charge)
          mooseError("C2 selected ion charge differs from signed S6 wall contract: ", id);
        selected.insert(id);
      }
    for (const auto & [id, record] : _data.speciesRecords())
      if (record.ion_wall)
        configured.insert(id);
    if (selected.empty() || configured != selected)
      mooseError("C2 selected fvm_species and species.<id>.wall_* producers differ");
    if (_data.surfaceElectronWallFlux().empty())
      mooseError("C2 requires ion_surface_current.electron_wall_number_flux");

    // No duplicated wall potential, gas-temperature or block fields in JSON.
    // The same Continuity action supplies potential and block to every
    // selected ion; [Plasmas] publishes the sole temperature Functor.
    if (!gasStateEnabled())
      mooseError("C2 wall flux requires [Plasmas] pressure and temperature");
    const auto blocks =
        continuity.front()->getParam<std::vector<SubdomainName>>("block");

    // Reject missing, extra, reordered/species-swapped or duplicate BCs.
    // A general FV Neumann BC owns five sidesets as one operator; each
    // dielectric BC owns one sideset, total four BC objects per species.
    const std::set<std::string> general_sides = {
        "inlet", "outlet", "plasma_electrode", "plasma_metal", "plasma_right"};
    const std::map<std::string, std::string> dielectric_sides = {
        {"cover", "plasma_cover"}, {"wafer", "plasma_wafer"},
        {"focus_ring", "plasma_focus_ring"}};
    std::set<std::string> seen;
    std::size_t count = 0;
    for (const auto & [group, boundary] : _data.boundaries())
      for (const auto & [name, bc] : boundary.bcs)
      {
        const bool normal = bc.type == "FVFunctorNeumannBC";
        const bool dielectric = bc.type == "FVLogMolarDielectricFluxBC";
        if (!normal && !dielectric)
          continue;
        ++count;
        if (bc.variable.rfind("log_", 0) != 0)
          mooseError("C2 FV BC variable must use log_<species>: ", name);
        const auto id = bc.variable.substr(4);
        if (!selected.count(id))
          mooseError("C2 FV BC targets unselected ion: ", name);
        const std::string flux = id + "_wall_number_flux";
        const std::set<std::string> sides(boundary.mesh_boundaries.begin(),
                                           boundary.mesh_boundaries.end());
        if (normal)
        {
          if (name != id + "_wall" || sides != general_sides || bc.functor != flux)
            mooseError("C2 general FV BC name/sideset/species Functor mismatch: ", name);
        }
        else
        {
          bool matched = false;
          for (const auto & [label, side] : dielectric_sides)
            if (name == id + "_" + label + "_dielectric" && sides == std::set<std::string>{side})
              matched = true;
          if (!matched || bc.signed_number_flux != flux)
            mooseError("C2 dielectric FV BC name/sideset/signed_number_flux mismatch: ", name);
        }
        if (!seen.insert(name).second)
          mooseError("C2 duplicate FV BC name: ", name);
      }
    for (const auto & id : selected)
    {
      if (!seen.count(id + "_wall"))
        mooseError("C2 missing general FV wall BC for ", id);
      for (const auto & [label, side] : dielectric_sides)
        if (!seen.count(id + "_" + label + "_dielectric"))
          mooseError("C2 missing dielectric wall BC for ", id, " on ", side);
    }
    if (count != 4 * selected.size())
      mooseError("C2 expected four ion wall BC objects per selected FV species, found ", count);

    if (_current_task == "add_functor_material")
    {
      for (const auto & id : selected)
      {
        const auto & wall = *_data.species(id).ion_wall;
        const auto type = "IonWallFluxMaterial";
        auto params = _factory.getValidParams(type);
        params.set<std::string>("species_id") = id;
        params.set<MooseFunctorName>("ion_number_density") = id + "_number_density";
        params.set<MooseFunctorName>("potential") = potential;
        params.set<MooseFunctorName>("mobility") = id + "_mobility";
        params.set<MooseFunctorName>("gas_temperature") = "temperature";
        params.set<Real>("charge_number") = _data.species(id).charge_number;
        params.set<Real>("molar_mass") = wall.molar_mass;
        params.set<Real>("sticking") = wall.sticking;
        params.set<Real>("ion_temperature_eV") = wall.ion_temperature_eV;
        params.set<Real>("migration_gate_smoothing_width") =
            continuity.front()->getParam<Real>("migration_smoothing_width");
        params.set<bool>("use_element_gradient_for_potential") =
            getParam<MooseEnum>("wall_gradient") == "adjacent_element";
        if (!blocks.empty())
          params.set<std::vector<SubdomainName>>("block") = blocks;
        _problem->addFunctorMaterial(type, id + "_wall", params);
      }

      // Preserve the three existing dielectric surface-current consumer names
      // and charge signs. These are derived from the SAME canonical wall Flux
      // Functors as the 12 FV BCs; electron ownership remains independent.
      std::vector<std::string> functors, symbols;
      std::string current_expression;
      for (const auto & id : {"O2p", "Op", "Om"})
        if (selected.count(id))
        {
          const std::string symbol = id == std::string("O2p") ? "gi" :
                                     id == std::string("Op") ? "gop" : "gm";
          functors.push_back(std::string(id) + "_wall_number_flux");
          symbols.push_back(symbol);
          current_expression +=
              (current_expression.empty() ? (_data.species(id).charge_number > 0 ? "" : "-")
                                          : (_data.species(id).charge_number > 0 ? "+" : "-")) +
              symbol;
        }
      functors.push_back(_data.surfaceElectronWallFlux());
      symbols.push_back("ge");
      current_expression += "-ge";
      for (const auto & side : {"cover", "wafer", "focus_ring"})
      {
        const auto type = "ADParsedFunctorMaterial";
        auto params = _factory.getValidParams(type);
        params.set<std::string>("property_name") =
            std::string(side) + "_net_surface_current_density";
        params.set<std::vector<std::string>>("functor_names") = functors;
        params.set<std::vector<std::string>>("functor_symbols") = symbols;
        params.set<std::string>("expression") =
            "1.602176634e-19*(" + current_expression + ")";
        if (!blocks.empty())
          params.set<std::vector<SubdomainName>>("block") = blocks;
        _problem->addFunctorMaterial(type, std::string(side) + "_surface_current", params);
      }
    }
  }

  // Root JSON is the sole ownership switch for the relocated, verbatim
  // [BCs] blocks, independent of the DD/NV taxonomy. There is deliberately NO .i
  // plasma_boundary toggle and NO implicit wall type interpretation.
  // This path also works when root gas_state is not enabled.
  if (_current_task == "add_bc" && _data.hasBoundaries())
    for (const auto & [group, boundary] : _data.boundaries())
      for (const auto & [name, bc] : boundary.bcs)
      {
        auto params = _factory.getValidParams(bc.type);
        params.set<NonlinearVariableName>("variable") = bc.variable;
        std::vector<BoundaryName> sidesets;
        for (const auto & side : boundary.mesh_boundaries)
          sidesets.emplace_back(side);
        params.set<std::vector<BoundaryName>>("boundary") = sidesets;
        if (bc.type == "FVFunctorNeumannBC")
        {
          params.set<MooseFunctorName>("functor") = bc.functor;
          // FVFunctorNeumannBC declares factor as a MooseFunctorName, not Real.
          // Preserve -1/N_A (~1e-24) at full precision; std::to_string would round it to zero.
          std::ostringstream factor_value;
          factor_value << std::setprecision(std::numeric_limits<Real>::max_digits10)
                       << bc.factor;
          params.set<MooseFunctorName>("factor") = factor_value.str();
          _problem->addFVBC(bc.type, name, params);
        }
        else if (bc.type == "FVLogMolarDielectricFluxBC")
        {
          params.set<MooseFunctorName>("signed_number_flux") = bc.signed_number_flux;
          _problem->addFVBC(bc.type, name, params);
        }
        else
        {
          params.set<MooseFunctorName>("wall_number_flux") = bc.wall_number_flux;
          if (bc.type == "FEMElectronEnergySheathBC")
            params.set<MooseFunctorName>("mean_energy") = bc.mean_energy;
          _problem->addBoundaryCondition(bc.type, name, params);
        }
      }

  if (!gasStateEnabled() ||
      (_current_task != "add_functor_material" &&
       _current_task != "add_ics_physics" && _current_task != "add_bc" &&
       _current_task != "add_postprocessor"))
    return;

  // In the archived S6 Navier-Stokes model pressure is a SOLVED FV
  // variable, not a separately produced constant Functor. A MOOSE FV
  // variable is itself a Functor. The root pressure parameter is its sole
  // initial-condition value; all live consumers use that variable under
  // the SAME name "pressure". Temperature remains root-owned and fixed.
  //
  // S6 has independently solved neutral mass fractions and its original
  // neutral EOS (rho_neutral); it does not claim an equivalent complete
  // JSON heavy-mixture catalogue. Never synthesize or renormalize missing
  // species fractions. A partially declared root mixture fails closed.
  if (_problem->hasVariable("pressure"))
  {
    bool has_root_composition = false;
    for (const auto & [id, record] : _data.speciesRecords())
      if (id != "e" &&
          (record.molar_mass_kg_mol > 0.0 ||
           record.initial_vol_mass_fraction ||
           record.initial_inlet_mass_fraction ||
           !record.mass_fraction_variable.empty() ||
           !record.mass_fraction_functor.empty()))
        has_root_composition = true;
    if (has_root_composition)
      paramError("files", "A solved Navier-Stokes pressure variable uses the "
                         "Native neutral composition closure; do not activate a "
                         "second root ideal-gas mixture owner.");
    if (isParamValid("sccm"))
      paramError("sccm", "A solved pressure cannot use root SCCM/mixture inlet "
                          "without a separately verified mixture contract.");
    if (_current_task == "add_ics_physics")
    {
      const auto type = "FVConstantIC";
      auto params = _factory.getValidParams(type);
      params.set<VariableName>("variable") = "pressure";
      params.set<Real>("value") = getParam<Real>("pressure");
      _problem->addFVInitialCondition(type, "plasma_initial_pressure", params);
    }
    else if (_current_task == "add_functor_material")
    {
      // MOOSE variables already provide AD Functor interfaces. Register no
      // Functor named pressure, p, p_fixed, T or T_g_fixed.
      const auto type = "ADGenericFunctorMaterial";
      auto params = _factory.getValidParams(type);
      params.set<std::vector<std::string>>("prop_names") = {"temperature"};
      std::ostringstream temperature;
      temperature << std::setprecision(17) << getParam<Real>("temperature");
      params.set<std::vector<MooseFunctorName>>("prop_values") = {temperature.str()};
      params.set<bool>("define_dot_functors") = false;
      _problem->addFunctorMaterial(type, "plasma_gas_temperature", params);

      // Keep total neutral particle density tied to the LIVE pressure
      // Functor and root temperature, never a frozen initial snapshot.
      auto gas = _factory.getValidParams("ADParsedFunctorMaterial");
      gas.set<std::string>("property_name") = "n_g";
      gas.set<std::string>("expression") =
          "pressure/(1.380649e-23*temperature)";
      gas.set<std::vector<std::string>>("functor_names") =
          {"pressure", "temperature"};
      gas.set<std::vector<std::string>>("functor_symbols") =
          {"pressure", "temperature"};
      _problem->addFunctorMaterial("ADParsedFunctorMaterial", "plasma_gas_n_g", gas);
    }
    return;
  }

  // No redundant top-level gas_state list. Composition is owned by each
  // Chemistry species, including explicitly zero heavy fractions.
  std::vector<std::string> species;
  std::vector<std::string> fractions;
  std::vector<Real> masses;
  double volume_sum = 0.0;
  double inlet_sum = 0.0;
  for (const auto & [id, record] : _data.speciesRecords())
  {
    if (id == "e")
      continue;
    if (record.molar_mass_kg_mol <= 0.0 ||
        !record.initial_vol_mass_fraction ||
        !record.initial_inlet_mass_fraction)
      paramError("files",
                 "Root ideal_gas requires molar_mass_kg_mol, initial_vol_mass_fraction "
                 "and initial_inlet_mass_fraction for every heavy species: ", id);

    if (record.mass_fraction_variable.empty() && record.mass_fraction_functor.empty())
      paramError("files", "Root ideal_gas requires one live mass_fraction_variable or "
                          "mass_fraction_functor for every heavy species: ", id);
    if (!record.mass_fraction_variable.empty() && !record.mass_fraction_functor.empty())
      paramError("files", "Duplicate live mass fraction owner for ", id);

    species.push_back(id);
    masses.push_back(record.molar_mass_kg_mol);
    volume_sum += *record.initial_vol_mass_fraction;
    inlet_sum += *record.initial_inlet_mass_fraction;
  }
  if (species.empty())
    paramError("files", "Root ideal_gas requires at least one heavy Chemistry species.");
  if (std::abs(volume_sum - 1.0) > 1e-8 || std::abs(inlet_sum - 1.0) > 1e-8)
    paramError("files", "Initial volume and inlet heavy-species mass fractions must each "
                        "sum to 1; received volume=", volume_sum, ", inlet=", inlet_sum);

  if (const auto * nv = _data.nvTransport())
  {
    std::set<std::string> active(nv->species.begin(), nv->species.end());
    std::set<std::string> catalogue(species.begin(), species.end());
    if (active != catalogue)
      paramError("files",
                 "Root ideal_gas requires NV transport species to match the complete "
                 "heavy gas composition; no implicit renormalization or silent omission.");
  }

  // A solved variable is the only source allowed to receive an FV IC or BC;
  // derived/constraint Functors are read-only and inherit the mixture closure.
  if (_current_task == "add_ics_physics")
  {
    for (const auto & id : species)
    {
      const auto & record = _data.species(id);
      if (record.mass_fraction_variable.empty())
        continue;
      const auto type = "FVConstantIC";
      auto params = _factory.getValidParams(type);
      params.set<VariableName>("variable") = record.mass_fraction_variable;
      params.set<Real>("value") = *record.initial_vol_mass_fraction;
      _problem->addFVInitialCondition(
          type, "plasma_initial_" + id + "_mass_fraction", params);
    }
    return;
  }
  if (_current_task == "add_bc")
  {
    if (isParamValid("sccm") &&
        getParam<MooseEnum>("inlet_species_bc_ownership") == "root_dirichlet")
      for (const auto & id : species)
      {
        const auto & record = _data.species(id);
        if (record.mass_fraction_variable.empty())
          continue;
        const std::string type = "FVDirichletBC";
        auto params = _factory.getValidParams(type);
        params.set<NonlinearVariableName>("variable") = record.mass_fraction_variable;
        params.set<std::vector<BoundaryName>>("boundary") =
            getParam<std::vector<BoundaryName>>("inlet_boundaries");
        params.set<Real>("value") = *record.initial_inlet_mass_fraction;
        _problem->addFVBC(type, "plasma_inlet_" + id + "_mass_fraction", params);
      }
    return;
  }

  if (_current_task == "add_postprocessor")
  {
    if (!isParamValid("sccm"))
      return;

    // The Action owns wiring only. SCCM physics and named value mapping
    // reside in the independent, once-evaluated SCCMInletFlow module.
    std::vector<Plasma::SCCMFeedSpecies> inlet_species;
    inlet_species.reserve(species.size());
    for (const auto & id : species)
    {
      const auto & record = _data.species(id);
      inlet_species.push_back(
          {id, *record.initial_inlet_mass_fraction, record.molar_mass_kg_mol});
    }
    const Plasma::SCCMFeedSettings settings{
        getParam<Real>("sccm"),
        getParam<Real>("inlet_area"),
        getParam<Real>("standard_molar_volume"),
        getParam<Real>("pressure"),
        getParam<Real>("temperature")};

    std::map<std::string, double> feed_values;
    try
    {
      feed_values = Plasma::SCCMInletFlow::calculate(settings, inlet_species);
    }
    catch (const std::invalid_argument & error)
    {
      paramError("sccm", "Invalid SCCM inlet feed: ", error.what());
    }

    for (const auto & [name, value] : feed_values)
    {
      const auto type = "ConstantPostprocessor";
      auto params = _factory.getValidParams(type);
      params.set<Real>("value") = value;
      _problem->addPostprocessor(type, name, params);
    }
    return;
  }

  // LIVE Y aliases retain their AD dependency on solver/constraint state.
  // The static initial/feed composition remains independent of live Y(t,x).
  for (const auto & id : species)
    fractions.push_back("Y_" + id);

  auto add = [this](const std::string & name,
                    const std::string & expression,
                    const std::vector<std::string> & functors,
                    const std::vector<std::string> & symbols)
  {
    auto params = _app.getFactory().getValidParams("ADParsedFunctorMaterial");
    params.set<std::string>("property_name") = name;
    params.set<std::string>("expression") = expression;
    if (!functors.empty())
    {
      params.set<std::vector<std::string>>("functor_names") = functors;
      params.set<std::vector<std::string>>("functor_symbols") = symbols;
    }
    _problem->addFunctorMaterial("ADParsedFunctorMaterial", "plasma_gas_" + name, params);
  };

  // Exactly one provider per gas state: root parameter pressure/temperature
  // publishes a same-named AD Functor; no p/T compatibility aliases.
  // MOOSE's numeric MooseFunctorName is a constant AD Functor. The underlying
  // formula and value are computed once; property names and AD API are stable.
  auto literal = [](const double value)
  {
    std::ostringstream stream;
    stream << std::setprecision(17) << value;
    return stream.str();
  };
  auto addStatic = [this, &literal](const std::string & name, const Real value)
  {
    const auto type = "ADGenericFunctorMaterial";
    auto params = _app.getFactory().getValidParams(type);
    params.set<std::vector<std::string>>("prop_names") = {name};
    params.set<std::vector<MooseFunctorName>>("prop_values") = {literal(value)};
    params.set<bool>("define_dot_functors") = false;
    _problem->addFunctorMaterial(type, "plasma_gas_" + name, params);
  };

  // The setup-only calculation has one physical owner, also reused by the
  // SCCM inlet module. No time-dependent solver value is snapshotted.
  std::vector<Plasma::IdealGasMixtureSpecies> initial_species;
  std::vector<Plasma::IdealGasMixtureSpecies> inlet_species;
  initial_species.reserve(species.size());
  inlet_species.reserve(species.size());
  for (const auto & id : species)
  {
    const auto & record = _data.species(id);
    initial_species.push_back(
        {id, *record.initial_vol_mass_fraction, record.molar_mass_kg_mol});
    inlet_species.push_back(
        {id, *record.initial_inlet_mass_fraction, record.molar_mass_kg_mol});
    addStatic("Y_" + id + "_initial_vol", *record.initial_vol_mass_fraction);
    addStatic("Y_" + id + "_inlet", *record.initial_inlet_mass_fraction);

    const auto & live = record.mass_fraction_variable.empty()
                           ? record.mass_fraction_functor
                           : record.mass_fraction_variable;
    if (live != "Y_" + id)
      add("Y_" + id, "live_y", {live}, {"live_y"});
  }

  Plasma::IdealGasMixtureValues initial;
  Plasma::IdealGasMixtureValues inlet;
  try
  {
    initial = Plasma::IdealGasMixtureState::evaluate(
        getParam<Real>("pressure"), getParam<Real>("temperature"), initial_species);
    inlet = Plasma::IdealGasMixtureState::evaluate(
        getParam<Real>("pressure"), getParam<Real>("temperature"), inlet_species);
  }
  catch (const std::invalid_argument & error)
  {
    paramError("files", "Invalid fixed ideal-gas mixture: ", error.what());
  }

  addStatic("pressure", getParam<Real>("pressure"));
  addStatic("temperature", getParam<Real>("temperature"));
  addStatic("n_g", initial.number_density_per_m3);
  addStatic("M_mix_initial", initial.molar_mass_kg_per_mol);
  addStatic("M_mix_inlet", inlet.molar_mass_kg_per_mol);
  addStatic("rho_g_initial", initial.density_kg_per_m3);
  addStatic("rho_g_inlet", inlet.density_kg_per_m3);

  // The equation of state consumes live Y_i when NV is activated; otherwise
  // this is a constant-composition, non-evolving gas-state closure.
  std::vector<std::string> names = {"pressure", "temperature"};
  std::vector<std::string> symbols = {"pressure", "temp"};
  std::string denominator;
  for (std::size_t i = 0; i < species.size(); ++i)
  {
    names.push_back(fractions[i]);
    const auto symbol = "y" + std::to_string(i);
    symbols.push_back(symbol);
    std::ostringstream mass;
    mass << std::setprecision(17) << masses[i];
    denominator += (denominator.empty() ? "" : "+") + symbol + "/" + mass.str();
  }
  add("rho_g", "pressure/(8.31446261815324*temp*(" + denominator + "))",
      names, symbols);
  add("M_mix", "1/(" + denominator + ")",
      std::vector<std::string>(names.begin() + 2, names.end()),
      std::vector<std::string>(symbols.begin() + 2, symbols.end()));
}

registerMooseAction("PhysicsApp", PlasmasAction, "check_integrity");
registerMooseAction("PhysicsApp", PlasmasAction, "add_functor_material");
registerMooseAction("PhysicsApp", PlasmasAction, "add_ics_physics");
registerMooseAction("PhysicsApp", PlasmasAction, "add_bc");
registerMooseAction("PhysicsApp", PlasmasAction, "add_postprocessor");
