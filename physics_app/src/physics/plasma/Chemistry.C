#include "Chemistry.h"

#include "nlohmann/json.hpp"

#include <cmath>
#include <iomanip>
#include <map>
#include <fstream>
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

} // namespace

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
          !entry.contains("progress_units") || !entry["progress_units"].is_string() ||
          !entry.contains("reactants") || !entry.contains("products"))
        fail(file, "reaction needs id, progress_units, reactants and products");
      if (entry.contains("progress"))
        fail(file, "progress is derived from reaction ID; remove the JSON progress field");
      ReactionRecord reaction;
      reaction.id = entry["id"].get<std::string>();
      reaction.progress = progressFromReactionId(reaction.id, file);
      if (!reaction_ids.insert(reaction.id).second ||
          !progresses.insert(reaction.progress).second)
        fail(file, "duplicate reaction ID or generated progress owner: " + reaction.id);
      if (entry["progress_units"].get<std::string>() != "mol/(m^3 s)")
        fail(file, reaction.id + ": progress must have mol/(m^3 s) units");
      if (!equation_ids.erase(reaction.id))
        fail(file, reaction.id + ": missing equation mapping");
      reaction.equation = root["equations"].at(reaction.id).get<std::string>();
      reaction.reactants = readCoefficients(entry["reactants"], file);
      reaction.products = readCoefficients(entry["products"], file);

      if (!entry.contains("electron_energy_change_eV"))
        fail(file, reaction.id + ": missing explicit electron energy policy");
      const auto & energy = entry["electron_energy_change_eV"];
      if (energy.is_number())
      {
        reaction.electron_energy_change_eV = energy.get<double>();
        if (!std::isfinite(reaction.electron_energy_change_eV))
          fail(file, reaction.id + ": nonfinite electron energy change");
        reaction.contributes_electron_energy = reaction.electron_energy_change_eV != 0.0;
      }
      else if (energy.is_object() && energy.value("model", std::string()) == "functor" &&
               energy.contains("name") && energy["name"].is_string())
      {
        reaction.electron_energy_change_functor = energy["name"].get<std::string>();
        if (reaction.electron_energy_change_functor.empty())
          fail(file, reaction.id + ": empty energy-change functor");
        reaction.contributes_electron_energy = true;
      }
      else if (!(energy.is_object() && energy.value("model", std::string()) == "none"))
        fail(file, reaction.id + ": energy change needs number, signed functor or model none");
      validateReaction(reaction, _species, file);
      _reactions.push_back(std::move(reaction));
    }
    if (!equation_ids.empty())
      fail(file, "equation without matching reaction ID: " + *equation_ids.begin());
  }
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
      if (!reaction.electron_energy_change_functor.empty())
      {
        // The energy-change functor itself has the signed eV/event contract.
        const auto delta = energy.symbol(reaction.electron_energy_change_functor);
        energy.parts.push_back("(" + delta + ")*" + progress);
      }
      else
        energy.parts.push_back("(" + realLiteral(reaction.electron_energy_change_eV) +
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
