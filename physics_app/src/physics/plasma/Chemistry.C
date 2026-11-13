#include "Chemistry.h"
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
parseDDTransport(const Json & value, const std::string & file)
{
  if (!value.is_object())
    fail(file, "drift_diffusion transport entry must be an object");
  DDTransportRecord result;
  result.model = requiredText(value, "model", file);
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
    for (const auto * excluded : {"table_file", "coordinate", "table_units",
                                   "pressure", "gas_temperature", "bounds_policy",
                                   "mobility_source", "diffusivity_source"})
      if (value.contains(excluded))
        fail(file, std::string("constant transport forbids ") + excluded);
  }
  else if (result.model == "functor")
  {
    // model=functor reuses the existing canonical species coefficient AD Functors.
    // Numeric physical constants remain model=constant with explicit mu and D.
    if (value.size() != 1)
      fail(file, "functor transport accepts only model; DDTransportMaterial derives "
                 "<species>_mobility and <species>_diffusivity.");
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

} // namespace

bool
DDTransportRecord::equals(const DDTransportRecord & rhs) const
{
  return model == rhs.model && mobility == rhs.mobility && diffusivity == rhs.diffusivity &&
         table_file == rhs.table_file &&
         table_units == rhs.table_units && pressure == rhs.pressure &&
         gas_temperature == rhs.gas_temperature && bounds_policy == rhs.bounds_policy;
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
    if (!root.is_object() || !root.contains("species") ||
        !root.contains("equations") || !root.contains("reactions") ||
        !root["species"].is_object() || !root["equations"].is_object() ||
        !root["reactions"].is_array())
      fail(file, "expected species object, equations object and reactions array");

    for (auto it = root["species"].begin(); it != root["species"].end(); ++it)
    {
      const auto & record = it.value();
      if (!record.is_object() || !record.contains("elements") ||
          !record["elements"].is_object() || !record.contains("charge_number") ||
          !record["charge_number"].is_number_integer())
        fail(file, "species '" + it.key() + "' requires elements and integer charge_number");
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
      // A continuity species' initial particle number density is JSON-owned,
      // independent of heavy-gas mass fractions and energy-density ICs.
      if (record.contains("initial_number_density"))
      {
        if (!record.at("initial_number_density").is_number())
          fail(file, "initial_number_density must be numeric for " + it.key());
        const double density = record.at("initial_number_density").get<double>();
        if (!std::isfinite(density) || density <= 0.0)
          fail(file, "initial_number_density must be finite and strictly positive [1/m^3] for " +
                     it.key());
        species.initial_number_density = density;
      }
      if (record.contains("molar_mass_kg_mol"))
      {
        if (!record.at("molar_mass_kg_mol").is_number())
          fail(file, "non-numeric molar_mass_kg_mol for " + it.key());
        species.molar_mass_kg_mol = record.at("molar_mass_kg_mol").get<double>();
        if (!std::isfinite(species.molar_mass_kg_mol) || species.molar_mass_kg_mol <= 0.0)
          fail(file, "molar_mass_kg_mol must be finite and positive for " + it.key());
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
        if (!existing->second.initial_number_density)
          existing->second.initial_number_density = species.initial_number_density;
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

    // The top-level JSON boundaries registry relocates existing named [BCs].
    // Absence of boundaries creates no additional BC objects.
    // No wall law, 'open' role, or additional implicit BC is invented.
    if (root.contains("drift_diffusion_boundary"))
      fail(file, "drift_diffusion_boundary is retired; use boundaries with physical mesh sideset keys");
    if (root.contains("boundaries"))
    {
      if (_has_boundaries)
        fail(file, "duplicate boundaries owner across JSON files");
      const auto & catalogue = root.at("boundaries");
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
        for (const auto & side : record.mesh_boundaries)
          if (!std::regex_match(side, identifier) ||
              !used_mesh_boundaries.insert(side).second)
            fail(file, "invalid or duplicate boundaries mesh sideset: " +
                           side);

        for (auto bc = item.at("bcs").begin(); bc != item.at("bcs").end(); ++bc)
        {
          const auto & spec = bc.value();
          if (!std::regex_match(bc.key(), identifier) ||
              !used_bc_names.insert(bc.key()).second)
            fail(file, "invalid or duplicate DriftDiffusion BC name: " + bc.key());
          if (!spec.is_object() || !spec.contains("type") || !spec.contains("variable") ||
              !spec.contains("wall_number_flux") || !spec.at("type").is_string() ||
              !spec.at("variable").is_string() ||
              !spec.at("wall_number_flux").is_string())
            fail(file, "boundaries BC " + bc.key() +
                           " requires type, variable, and wall_number_flux strings");

          BoundaryBCRecord entry;
          entry.type = spec.at("type").get<std::string>();
          entry.variable = spec.at("variable").get<std::string>();
          entry.wall_number_flux = spec.at("wall_number_flux").get<std::string>();
          const bool particle = entry.type == "FEMElectronSheathBC";
          const bool energy = entry.type == "FEMElectronEnergySheathBC";
          if (!particle && !energy)
            fail(file, "boundaries BC type is not yet supported: " +
                           entry.type + " for " + bc.key());
          if (spec.size() != (particle ? 3 : 4) ||
              (energy && (!spec.contains("mean_energy") ||
                          !spec.at("mean_energy").is_string())))
            fail(file, "wrong named arguments in boundaries BC " + bc.key());
          if (energy)
            entry.mean_energy = spec.at("mean_energy").get<std::string>();
          if (entry.variable.empty() || entry.wall_number_flux.empty() ||
              (energy && entry.mean_energy.empty()))
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

    // Multiple chemistry files may contribute reactions independently, but
    // coefficient owners are one per species and one per NV mixture.
    if (root.contains("transport_coefficients"))
    {
      const auto & coefficients = root.at("transport_coefficients");
      if (!coefficients.is_object())
        fail(file, "transport_coefficients must be an object");
      for (auto it = coefficients.begin(); it != coefficients.end(); ++it)
        if (it.key() != "drift_diffusion" && it.key() != "navier_stokes")
          fail(file, "unknown transport_coefficients section: " + it.key());

      if (coefficients.contains("drift_diffusion"))
      {
        const auto & owners = coefficients.at("drift_diffusion");
        if (!owners.is_object())
          fail(file, "transport_coefficients.drift_diffusion must be an object");
        for (auto it = owners.begin(); it != owners.end(); ++it)
        {
          if (it.key() == "e_energy")
          {
            // This is a closure selector, not a separate particle DD
            // Material and not a Chemistry reaction species.
            const auto & energy = it.value();
            if (!energy.is_object() || energy.size() != 1 ||
                !energy.contains("type") || !energy.at("type").is_string() ||
                energy.at("type").get<std::string>() != "fluid")
              fail(file, "e_energy transport requires exactly {\"type\":\"fluid\"}.");
            if (_fluid_electron_energy_transport)
              fail(file, "duplicate e_energy transport closure owner");
            _fluid_electron_energy_transport = true;
            continue;
          }
          const auto record = parseDDTransport(it.value(), file);
          const auto previous = _dd_transport.find(it.key());
          if (previous == _dd_transport.end())
            _dd_transport.emplace(it.key(), record);
          else if (!previous->second.equals(record))
            fail(file, "conflicting drift_diffusion coefficient owner for " + it.key());
        }
      }
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
         "e_energy type=fluid requires an electron e drift_diffusion transport record");
  for (const auto & [id, config] : _dd_transport)
    if (_species.find(id) == _species.end())
      fail("<merged plasma mechanism>", "transport_coefficients references unknown species: " + id);
  if (_nv_transport)
    for (const auto & id : _nv_transport->species)
      if (_species.find(id) == _species.end())
        fail("<merged plasma mechanism>", "navier_stokes references unknown species: " + id);
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
  params.addParam<Real>("pressure", "Uniform gas pressure [Pa]; enables canonical Gas State.");
  params.addParam<Real>("temperature", "Uniform gas temperature [K]; enables canonical Gas State.");
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
        params.set<MooseFunctorName>("wall_number_flux") = bc.wall_number_flux;
        if (bc.type == "FEMElectronEnergySheathBC")
          params.set<MooseFunctorName>("mean_energy") = bc.mean_energy;
        _problem->addBoundaryCondition(bc.type, name, params);
      }

  if (!gasStateEnabled() ||
      (_current_task != "add_functor_material" &&
       _current_task != "add_ics_physics" && _current_task != "add_bc" &&
       _current_task != "add_postprocessor"))
    return;

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

  addStatic("p", getParam<Real>("pressure"));
  addStatic("T", getParam<Real>("temperature"));
  addStatic("n_g", initial.number_density_per_m3);
  addStatic("M_mix_initial", initial.molar_mass_kg_per_mol);
  addStatic("M_mix_inlet", inlet.molar_mass_kg_per_mol);
  addStatic("rho_g_initial", initial.density_kg_per_m3);
  addStatic("rho_g_inlet", inlet.density_kg_per_m3);

  // The equation of state consumes live Y_i when NV is activated; otherwise
  // this is a constant-composition, non-evolving gas-state closure.
  std::vector<std::string> names = {"p", "T"};
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
