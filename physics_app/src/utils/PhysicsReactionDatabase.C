#include "PhysicsReactionDatabase.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace
{
std::runtime_error
parseError(const std::string & filename, unsigned int line, const std::string & message)
{
  std::ostringstream oss;
  oss << "PhysicsReactionDatabase parse error in '" << filename << "' at line " << line << ": "
      << message;
  return std::runtime_error(oss.str());
}

bool
nearlyZero(double value, double scale)
{
  return std::abs(value) <= 1.0e-12 * std::max(1.0, scale);
}
}

PhysicsReactionDatabase::PhysicsReactionDatabase(const std::string & filename)
{
  load(filename);
}

std::string
PhysicsReactionDatabase::trim(const std::string & value)
{
  const auto first = value.find_first_not_of(" \t\r\n");
  if (first == std::string::npos)
    return "";

  const auto last = value.find_last_not_of(" \t\r\n");
  return value.substr(first, last - first + 1);
}

PhysicsReactionDatabase::SpeciesKind
PhysicsReactionDatabase::parseSpeciesKind(const std::string & value)
{
  if (value == "heavy")
    return SpeciesKind::Heavy;
  if (value == "electron")
    return SpeciesKind::Electron;

  throw std::runtime_error("Unknown species kind '" + value + "'.");
}

PhysicsReactionDatabase::Domain
PhysicsReactionDatabase::parseDomain(const std::string & value)
{
  if (value == "volume")
    return Domain::Volume;
  if (value == "surface")
    return Domain::Surface;

  throw std::runtime_error("Unknown reaction domain '" + value + "'.");
}

PhysicsReactionDatabase::RateModel
PhysicsReactionDatabase::parseRateModel(const std::string & value)
{
  if (value == "constant")
    return RateModel::Constant;
  if (value == "power_law")
    return RateModel::PowerLaw;
  if (value == "thermal_sticking")
    return RateModel::ThermalSticking;
  if (value == "deferred_charged_flux")
    return RateModel::DeferredChargedFlux;

  throw std::runtime_error("Unknown rate model '" + value + "'.");
}

PhysicsReactionDatabase::RateBasis
PhysicsReactionDatabase::parseRateBasis(const std::string & value)
{
  if (value == "molar")
    return RateBasis::Molar;
  if (value == "particle")
    return RateBasis::Particle;

  throw std::runtime_error("Unknown rate basis '" + value + "'.");
}

std::size_t
PhysicsReactionDatabase::speciesIndex(const std::string & name) const
{
  const auto it = _species_index.find(name);
  if (it == _species_index.end())
    throw std::runtime_error("Unknown chemistry species '" + name + "'.");

  return it->second;
}

std::size_t
PhysicsReactionDatabase::reactionIndex(const std::string & name) const
{
  const auto it = _reaction_index.find(name);
  if (it == _reaction_index.end())
    throw std::runtime_error("Unknown chemistry reaction '" + name + "'.");

  return it->second;
}

const PhysicsReactionDatabase::Species &
PhysicsReactionDatabase::species(const std::string & name) const
{
  return _species.at(speciesIndex(name));
}

const PhysicsReactionDatabase::Reaction &
PhysicsReactionDatabase::reaction(const std::string & name) const
{
  return _reactions.at(reactionIndex(name));
}

double
PhysicsReactionDatabase::stoichCoefficient(const Reaction & reaction,
                                           std::size_t species_index) const
{
  double nu = 0.0;

  for (const auto & term : reaction.products)
    if (term.species_index == species_index)
      nu += term.coefficient;

  for (const auto & term : reaction.reactants)
    if (term.species_index == species_index)
      nu -= term.coefficient;

  return nu;
}

double
PhysicsReactionDatabase::heavyMassImbalance(const Reaction & reaction) const
{
  double imbalance = 0.0;

  for (std::size_t i = 0; i < _species.size(); ++i)
    if (_species[i].kind == SpeciesKind::Heavy)
      imbalance += stoichCoefficient(reaction, i) * _species[i].molar_mass;

  return imbalance;
}

double
PhysicsReactionDatabase::chargeImbalance(const Reaction & reaction) const
{
  double imbalance = 0.0;

  for (std::size_t i = 0; i < _species.size(); ++i)
    imbalance += stoichCoefficient(reaction, i) * static_cast<double>(_species[i].charge);

  return imbalance;
}

void
PhysicsReactionDatabase::finalizeReaction(Reaction & reaction,
                                          bool have_A,
                                          bool have_basis,
                                          bool have_sticking,
                                          const std::string & filename,
                                          unsigned int line_number)
{
  if (reaction.reactants.empty())
    throw parseError(filename, line_number, "Reaction '" + reaction.name + "' has no reactants.");

  if (reaction.products.empty())
    throw parseError(filename, line_number, "Reaction '" + reaction.name + "' has no products.");

  reaction.reaction_order = 0.0;
  for (const auto & term : reaction.reactants)
  {
    if (term.coefficient <= 0.0)
      throw parseError(filename,
                       line_number,
                       "Reaction '" + reaction.name + "' has a non-positive reactant coefficient.");
    reaction.reaction_order += term.coefficient;
  }

  if (reaction.domain == Domain::Volume)
  {
    if (reaction.model != RateModel::Constant && reaction.model != RateModel::PowerLaw)
      throw parseError(filename,
                       line_number,
                       "Volume reaction '" + reaction.name + "' uses a non-volume rate model.");

    if (!have_A || !have_basis)
      throw parseError(filename,
                       line_number,
                       "Volume reaction '" + reaction.name +
                           "' must define both A and basis.");

    if (reaction.A_input < 0.0)
      throw parseError(filename, line_number, "Reaction prefactor A must be non-negative.");

    if (reaction.model == RateModel::PowerLaw && reaction.T_ref <= 0.0)
      throw parseError(filename, line_number, "Power-law T_ref must be positive.");

    reaction.A_molar = reaction.A_input;
    if (reaction.basis == RateBasis::Particle)
      reaction.A_molar *=
          std::pow(avogadro(), std::max(0.0, reaction.reaction_order - 1.0));

    const auto mass_error = heavyMassImbalance(reaction);
    double mass_scale = 0.0;
    for (const auto & term : reaction.reactants)
      if (_species[term.species_index].kind == SpeciesKind::Heavy)
        mass_scale += term.coefficient * _species[term.species_index].molar_mass;

    if (!nearlyZero(mass_error, mass_scale))
      throw parseError(filename,
                       line_number,
                       "Heavy-mass imbalance in volume reaction '" + reaction.name + "'.");

    const auto charge_error = chargeImbalance(reaction);
    if (!nearlyZero(charge_error, 1.0))
      throw parseError(filename,
                       line_number,
                       "Charge imbalance in volume reaction '" + reaction.name + "'.");
  }
  else
  {
    if (reaction.model != RateModel::ThermalSticking &&
        reaction.model != RateModel::DeferredChargedFlux)
      throw parseError(filename,
                       line_number,
                       "Surface reaction '" + reaction.name + "' uses a non-surface model.");

    if (!have_sticking)
      throw parseError(filename,
                       line_number,
                       "Surface reaction '" + reaction.name + "' must define sticking.");

    if (reaction.sticking < 0.0)
      throw parseError(filename, line_number, "Sticking coefficient must be non-negative.");

    const auto mass_error = heavyMassImbalance(reaction);
    double mass_scale = 0.0;
    for (const auto & term : reaction.reactants)
      if (_species[term.species_index].kind == SpeciesKind::Heavy)
        mass_scale += term.coefficient * _species[term.species_index].molar_mass;

    if (!nearlyZero(mass_error, mass_scale))
      throw parseError(filename,
                       line_number,
                       "Heavy-mass imbalance in surface reaction '" + reaction.name + "'.");

    // Surface charge need not balance within the plasma species set because the
    // wall carries the compensating current.
  }

  if (_reaction_index.count(reaction.name))
    throw parseError(filename,
                     line_number,
                     "Duplicate reaction name '" + reaction.name + "'.");

  _reaction_index[reaction.name] = _reactions.size();
  _reactions.push_back(reaction);
}

void
PhysicsReactionDatabase::load(const std::string & filename)
{
  std::ifstream in(filename);
  if (!in.good())
    throw std::runtime_error("PhysicsReactionDatabase could not open chemistry file '" + filename + "'.");

  bool in_reaction = false;
  Reaction current;
  bool have_A = false;
  bool have_basis = false;
  bool have_sticking = false;

  std::string line;
  unsigned int line_number = 0;

  while (std::getline(in, line))
  {
    ++line_number;

    const auto hash = line.find('#');
    if (hash != std::string::npos)
      line.erase(hash);

    line = trim(line);
    if (line.empty())
      continue;

    std::istringstream iss(line);
    std::string keyword;
    iss >> keyword;

    try
    {
      if (!in_reaction)
      {
        if (keyword == "species")
        {
          Species species;
          std::string kind;

          if (!(iss >> species.name >> species.solver_id >> species.molar_mass >> species.charge >>
                kind))
            throw parseError(filename,
                             line_number,
                             "Expected: species <chem_name> <solver_id> "
                             "<molar_mass_kg_per_mol> <charge> <kind>");

          species.kind = parseSpeciesKind(kind);

          if (_species_index.count(species.name))
            throw parseError(filename,
                             line_number,
                             "Duplicate species name '" + species.name + "'.");

          for (const auto & existing : _species)
            if (existing.solver_id == species.solver_id)
              throw parseError(filename,
                               line_number,
                               "Duplicate solver_id '" + species.solver_id + "'.");

          if (species.kind == SpeciesKind::Heavy && species.molar_mass <= 0.0)
            throw parseError(filename,
                             line_number,
                             "Heavy species '" + species.name + "' must have positive molar mass.");

          if (species.kind == SpeciesKind::Electron && species.molar_mass < 0.0)
            throw parseError(filename,
                             line_number,
                             "Electron molar mass metadata must be non-negative.");

          _species_index[species.name] = _species.size();
          _species.push_back(species);
        }
        else if (keyword == "reaction")
        {
          std::string domain;
          std::string model;

          current = Reaction();
          have_A = false;
          have_basis = false;
          have_sticking = false;

          if (!(iss >> current.name >> domain >> model))
            throw parseError(filename,
                             line_number,
                             "Expected: reaction <name> <domain> <model>");

          current.domain = parseDomain(domain);
          current.model = parseRateModel(model);
          in_reaction = true;
        }
        else
          throw parseError(filename, line_number, "Unknown top-level keyword '" + keyword + "'.");
      }
      else
      {
        if (keyword == "reactant" || keyword == "product")
        {
          std::string species_name;
          double coefficient = 0.0;

          if (!(iss >> species_name >> coefficient))
            throw parseError(filename,
                             line_number,
                             "Expected: " + keyword + " <species> <stoich>");

          const StoichTerm term{speciesIndex(species_name), coefficient};

          if (keyword == "reactant")
            current.reactants.push_back(term);
          else
            current.products.push_back(term);
        }
        else if (keyword == "A")
        {
          if (!(iss >> current.A_input))
            throw parseError(filename, line_number, "Expected: A <prefactor>");
          have_A = true;
        }
        else if (keyword == "basis")
        {
          std::string basis;
          if (!(iss >> basis))
            throw parseError(filename, line_number, "Expected: basis <particle|molar>");
          current.basis = parseRateBasis(basis);
          have_basis = true;
        }
        else if (keyword == "T_ref")
        {
          if (!(iss >> current.T_ref))
            throw parseError(filename, line_number, "Expected: T_ref <K>");
        }
        else if (keyword == "exponent")
        {
          if (!(iss >> current.exponent))
            throw parseError(filename, line_number, "Expected: exponent <value>");
        }
        else if (keyword == "sticking")
        {
          if (!(iss >> current.sticking))
            throw parseError(filename, line_number, "Expected: sticking <value>");
          have_sticking = true;
        }
        else if (keyword == "extra")
        {
          current.extra.clear();
          double value = 0.0;
          while (iss >> value)
            current.extra.push_back(value);
        }
        else if (keyword == "end")
        {
          finalizeReaction(
              current, have_A, have_basis, have_sticking, filename, line_number);
          in_reaction = false;
        }
        else
          throw parseError(filename,
                           line_number,
                           "Unknown reaction keyword '" + keyword + "'.");
      }
    }
    catch (const std::runtime_error &)
    {
      throw;
    }
  }

  if (in_reaction)
    throw parseError(filename, line_number, "Reaction block was not terminated by 'end'.");

  if (_species.empty())
    throw std::runtime_error("PhysicsReactionDatabase chemistry file contains no species.");

  if (_reactions.empty())
    throw std::runtime_error("PhysicsReactionDatabase chemistry file contains no reactions.");
}
