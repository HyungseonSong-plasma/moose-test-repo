#include "PhysicsReactionRateMaterial.h"

#include <cmath>
#include <set>
#include <stdexcept>

registerMooseObject("PhysicsApp", PhysicsReactionRateMaterial);

InputParameters
PhysicsReactionRateMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Evaluates data-driven heavy-particle volume reaction rates and publishes one "
      "canonical molar reaction-progress functor per active reaction. Downstream "
      "source projectors must reuse those progress functors.");

  params.addRequiredParam<FileName>("chemistry_file", "Physics chemistry database.");
  params.addRequiredParam<MooseFunctorName>("density", "Heavy-mixture density [kg/m^3].");
  params.addRequiredParam<MooseFunctorName>("temperature", "Heavy-particle temperature [K].");

  params.addRequiredParam<std::vector<std::string>>(
      "species",
      "Chemistry species names whose mass fractions are supplied.");

  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "mass_fractions",
      "Mass-fraction functors in the same order as 'species'.");

  params.addParam<std::vector<std::string>>(
      "active_reactions",
      {},
      "Optional volume-reaction names to activate. If empty, all volume reactions "
      "whose reactants are available from the supplied species are activated.");

  return params;
}

PhysicsReactionRateMaterial::PhysicsReactionRateMaterial(const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _density(getFunctor<ADReal>("density")),
    _temperature(getFunctor<ADReal>("temperature")),
    _database(getParam<FileName>("chemistry_file")),
    _active_species_names(getParam<std::vector<std::string>>("species")),
    _mass_fraction_names(getParam<std::vector<MooseFunctorName>>("mass_fractions"))
{
  if (_active_species_names.size() != _mass_fraction_names.size())
    paramError("mass_fractions",
               "'species' and 'mass_fractions' must have the same number of entries.");

  std::set<std::size_t> seen_species;
  for (std::size_t i = 0; i < _active_species_names.size(); ++i)
  {
    std::size_t db_index = 0;
    try
    {
      db_index = _database.speciesIndex(_active_species_names[i]);
    }
    catch (const std::runtime_error & error)
    {
      paramError("species", error.what());
    }

    const auto & species = _database.species().at(db_index);
    if (species.kind != PhysicsReactionDatabase::SpeciesKind::Heavy)
      paramError("species",
                 "Mass-fraction input may only be supplied for heavy species. '",
                 species.name,
                 "' is not heavy.");

    if (!seen_species.insert(db_index).second)
      paramError("species", "Duplicate active species '", species.name, "'.");

    _mass_fraction_by_database_species[db_index] =
        &getFunctorByName<ADReal>(_mass_fraction_names[i]);
  }

  const auto requested = getParam<std::vector<std::string>>("active_reactions");

  if (!requested.empty())
  {
    for (const auto & name : requested)
    {
      std::size_t index = 0;
      try
      {
        index = _database.reactionIndex(name);
      }
      catch (const std::runtime_error & error)
      {
        paramError("active_reactions", error.what());
      }

      const auto & reaction = _database.reactions().at(index);
      if (reaction.domain != PhysicsReactionDatabase::Domain::Volume)
        paramError("active_reactions",
                   "Reaction '",
                   name,
                   "' is not a volume reaction.");

      for (const auto & reactant : reaction.reactants)
      {
        const auto & species = _database.species().at(reactant.species_index);
        if (species.kind == PhysicsReactionDatabase::SpeciesKind::Electron)
          paramError("active_reactions",
                     "Electron-reactant volume reactions are reserved for the electron "
                     "lookup closure and cannot be activated here.");

        if (!_mass_fraction_by_database_species.count(reactant.species_index))
          paramError("active_reactions",
                     "Reaction '",
                     name,
                     "' requires reactant '",
                     species.name,
                     "', but no mass-fraction functor was supplied for it.");
      }

      _active_reactions.push_back(index);
    }
  }
  else
  {
    for (std::size_t index = 0; index < _database.reactions().size(); ++index)
    {
      const auto & reaction = _database.reactions()[index];
      if (reaction.domain != PhysicsReactionDatabase::Domain::Volume)
        continue;

      bool compatible = true;
      for (const auto & reactant : reaction.reactants)
      {
        const auto & species = _database.species().at(reactant.species_index);
        if (species.kind == PhysicsReactionDatabase::SpeciesKind::Electron ||
            !_mass_fraction_by_database_species.count(reactant.species_index))
        {
          compatible = false;
          break;
        }
      }

      if (compatible)
        _active_reactions.push_back(index);
    }
  }

  for (const auto reaction_index : _active_reactions)
  {
    const auto & reaction = _database.reactions().at(reaction_index);
    addFunctorProperty<ADReal>(
        "reaction_rate_" + reaction.name,
        [this, reaction_index](const auto & r, const auto & state) -> ADReal
        { return reactionProgress(_database.reactions().at(reaction_index), r, state); });
  }
}

template <typename SpaceArg, typename StateArg>
ADReal
PhysicsReactionRateMaterial::concentration(std::size_t database_species,
                                           const SpaceArg & r,
                                           const StateArg & state) const
{
  const auto it = _mass_fraction_by_database_species.find(database_species);
  if (it == _mass_fraction_by_database_species.end())
    mooseError("No mass-fraction functor is available for chemistry species '",
               _database.species()[database_species].name,
               "'.");

  const auto molar_mass = _database.species()[database_species].molar_mass;
  return _density(r, state) * (*(it->second))(r, state) / molar_mass;
}

template <typename SpaceArg, typename StateArg>
ADReal
PhysicsReactionRateMaterial::reactionProgress(const PhysicsReactionDatabase::Reaction & reaction,
                                              const SpaceArg & r,
                                              const StateArg & state) const
{
  using std::pow;

  const ADReal T = _temperature(r, state);

  ADReal k = reaction.A_molar;
  if (reaction.model == PhysicsReactionDatabase::RateModel::PowerLaw)
    k *= pow(reaction.T_ref / T, reaction.exponent);

  ADReal progress = k;
  for (const auto & reactant : reaction.reactants)
  {
    const ADReal c = concentration(reactant.species_index, r, state);

    if (std::abs(reactant.coefficient - 1.0) < 1.0e-14)
      progress *= c;
    else
      progress *= pow(c, reactant.coefficient);
  }

  return progress;
}
