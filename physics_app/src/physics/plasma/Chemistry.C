#include "Chemistry.h"

#include "nlohmann/json.hpp"

#include <cmath>
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
  if (charge_balance != 0)
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
  else if (result.model == "constants")
  {
    // JSON model=constants reuses the canonical, existing species coefficient
    // Functors published upstream. It is NOT the numerical constant mode;
    // model=constant with explicit values is distinct.
    if (value.size() != 1)
      fail(file, "constants transport accepts only model; DDMaterial derives "
                 "<species>_mobility and <species>_diffusivity.");
  }
  else if (result.model == "lookup")
  {
    if (value.contains("mobility") || value.contains("diffusivity") ||
        value.contains("mobility_source") || value.contains("diffusivity_source"))
      fail(file, "lookup transport forbids constant or Functor coefficient inputs");
    result.table_file = resolveDataFile(requiredText(value, "table_file", file), file);
    // Lookup always uses the canonical solved electron mean-energy Functor:
    // mean_en_solved. The JSON schema must not expose its coordinate name.
    if (value.contains("coordinate") || value.contains("mean_energy"))
      fail(file, "DD lookup coordinate is implicit: mean_en_solved; do not specify coordinate.");
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
    fail(file, "transport model must be 'lookup', 'constant' or 'constants'");
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
      const auto existing = _species.find(it.key());
      if (existing == _species.end())
        _species.emplace(it.key(), species);
      else if (existing->second.charge_number != species.charge_number ||
               existing->second.elements != species.elements)
        fail(file, "conflicting species identity for " + it.key());
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
      if (entry["units"].get<std::string>() != "mol/(m^3 s)")
        fail(file, reaction.id + ": progress must have mol/(m^3 s) units");
      if (!equation_ids.erase(reaction.id))
        fail(file, reaction.id + ": missing equation mapping");
      reaction.equation = root["equations"].at(reaction.id).get<std::string>();
      reaction.reactants = readCoefficients(entry["reactants"], file);
      reaction.products = readCoefficients(entry["products"], file);

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
    if (reaction.net(id) != 0)
      return true;
  return false;
}

bool
ChemistryData::hasElectronEnergySource() const
{
  for (const auto & reaction : _reactions)
    if (reaction.contributes_electron_energy)
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
      "files", {}, "Ordered JSON mechanism files shared by plasma Chemistry, Continuity and Poisson.");
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
}

registerMooseAction("PhysicsApp", PlasmasAction, "check_integrity");
