#include "PlasmaMechanism.h"

#include "nlohmann/json.hpp"

#include <cmath>
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

PlasmaMechanism::PlasmaMechanism(const std::vector<std::string> & files)
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
          !entry.contains("progress") || !entry["progress"].is_string() ||
          !entry.contains("progress_units") || !entry["progress_units"].is_string() ||
          !entry.contains("reactants") || !entry.contains("products"))
        fail(file, "reaction needs id, progress, progress_units, reactants and products");
      ReactionRecord reaction;
      reaction.id = entry["id"].get<std::string>();
      reaction.progress = entry["progress"].get<std::string>();
      if (reaction.id.empty() || reaction.progress.empty() ||
          !reaction_ids.insert(reaction.id).second ||
          !progresses.insert(reaction.progress).second)
        fail(file, "duplicate/empty reaction ID or progress owner: " + reaction.id);
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
PlasmaMechanism::species(const std::string & id) const
{
  auto it = _species.find(id);
  if (it == _species.end())
    throw std::runtime_error("Species '" + id + "' is absent from [Plasmas]/files");
  return it->second;
}

bool
PlasmaMechanism::hasSpeciesSource(const std::string & id) const
{
  for (const auto & reaction : _reactions)
    if (reaction.net(id) != 0)
      return true;
  return false;
}

bool
PlasmaMechanism::hasElectronEnergySource() const
{
  for (const auto & reaction : _reactions)
    if (reaction.contributes_electron_energy)
      return true;
  return false;
}

} // namespace Plasma
