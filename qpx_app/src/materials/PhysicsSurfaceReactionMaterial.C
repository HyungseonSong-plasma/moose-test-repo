#include "PhysicsSurfaceReactionMaterial.h"

#include <cmath>
#include <set>
#include <stdexcept>

registerMooseObject("PhysicsApp", PhysicsSurfaceReactionMaterial);

InputParameters
PhysicsSurfaceReactionMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Evaluates data-driven neutral thermal-sticking surface reactions and "
      "provides signed outward species mass-flux functors.");

  params.addRequiredParam<FileName>("chemistry_file", "Physics chemistry database.");
  params.addRequiredParam<MooseFunctorName>("density", "Heavy-mixture density [kg/m^3].");
  params.addRequiredParam<MooseFunctorName>("temperature", "Heavy-particle temperature [K].");

  params.addRequiredParam<std::vector<std::string>>(
      "species",
      "Heavy chemistry species names whose mass fractions are supplied.");

  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "mass_fractions",
      "Mass-fraction functors in the same order as 'species'.");

  params.addParam<std::vector<std::string>>(
      "active_reactions",
      {},
      "Optional thermal-sticking surface reactions to activate. If empty, all "
      "compatible thermal-sticking reactions are activated.");

  return params;
}

PhysicsSurfaceReactionMaterial::PhysicsSurfaceReactionMaterial(const InputParameters & parameters)
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
                 "Surface mass fractions may only be supplied for heavy species.");

    if (!seen_species.insert(db_index).second)
      paramError("species", "Duplicate active species '", species.name, "'.");

    _mass_fraction_by_database_species[db_index] =
        &getFunctorByName<ADReal>(_mass_fraction_names[i]);
  }

  const auto requested = getParam<std::vector<std::string>>("active_reactions");

  auto check_and_add = [this](std::size_t index)
  {
    const auto & reaction = _database.reactions().at(index);

    if (reaction.domain != PhysicsReactionDatabase::Domain::Surface ||
        reaction.model != PhysicsReactionDatabase::RateModel::ThermalSticking)
      paramError("active_reactions",
                 "Reaction '",
                 reaction.name,
                 "' is not a neutral thermal-sticking surface reaction.");

    if (reaction.reactants.size() != 1)
      paramError("active_reactions",
                 "Thermal-sticking v1 requires exactly one incident reactant in reaction '",
                 reaction.name,
                 "'.");

    const auto reactant_index = reaction.reactants.front().species_index;
    const auto & reactant = _database.species().at(reactant_index);

    if (reactant.kind != PhysicsReactionDatabase::SpeciesKind::Heavy || reactant.charge != 0)
      paramError("active_reactions",
                 "Thermal-sticking v1 accepts neutral heavy reactants only. Reaction '",
                 reaction.name,
                 "' must use the deferred charged-flux model instead.");

    if (!_mass_fraction_by_database_species.count(reactant_index))
      paramError("active_reactions",
                 "Reaction '",
                 reaction.name,
                 "' requires reactant '",
                 reactant.name,
                 "', but no mass-fraction functor was supplied.");

    _active_reactions.push_back(index);
  };

  if (!requested.empty())
  {
    for (const auto & name : requested)
    {
      try
      {
        check_and_add(_database.reactionIndex(name));
      }
      catch (const std::runtime_error & error)
      {
        paramError("active_reactions", error.what());
      }
    }
  }
  else
  {
    for (std::size_t index = 0; index < _database.reactions().size(); ++index)
    {
      const auto & reaction = _database.reactions()[index];
      if (reaction.domain != PhysicsReactionDatabase::Domain::Surface ||
          reaction.model != PhysicsReactionDatabase::RateModel::ThermalSticking ||
          reaction.reactants.size() != 1)
        continue;

      if (_mass_fraction_by_database_species.count(reaction.reactants.front().species_index))
        check_and_add(index);
    }
  }

  for (const auto reaction_index : _active_reactions)
  {
    const auto & reaction = _database.reactions().at(reaction_index);
    addFunctorProperty<ADReal>(
        "surface_reaction_rate_" + reaction.name,
        [this, reaction_index](const auto & r, const auto & state) -> ADReal
        { return reactionProgress(_database.reactions().at(reaction_index), r, state); });
  }

  for (std::size_t species_index = 0; species_index < _database.species().size(); ++species_index)
  {
    const auto & species = _database.species()[species_index];
    if (species.kind != PhysicsReactionDatabase::SpeciesKind::Heavy)
      continue;

    addFunctorProperty<ADReal>(
        "surface_mass_flux_" + species.solver_id,
        [this, species_index](const auto & r, const auto & state) -> ADReal
        { return outwardMassFlux(species_index, r, state); });
  }

  addFunctorProperty<ADReal>(
      "surface_mass_flux_sum",
      [this](const auto & r, const auto & state) -> ADReal
      {
        ADReal sum = 0.0;
        for (std::size_t i = 0; i < _database.species().size(); ++i)
          if (_database.species()[i].kind == PhysicsReactionDatabase::SpeciesKind::Heavy)
            sum += outwardMassFlux(i, r, state);
        return sum;
      });
}

template <typename SpaceArg, typename StateArg>
ADReal
PhysicsSurfaceReactionMaterial::concentration(std::size_t database_species,
                                          const SpaceArg & r,
                                          const StateArg & state) const
{
  const auto it = _mass_fraction_by_database_species.find(database_species);
  if (it == _mass_fraction_by_database_species.end())
    mooseError("No mass-fraction functor is available for surface-reactant species '",
               _database.species()[database_species].name,
               "'.");

  const auto molar_mass = _database.species()[database_species].molar_mass;
  return _density(r, state) * (*(it->second))(r, state) / molar_mass;
}

template <typename SpaceArg, typename StateArg>
ADReal
PhysicsSurfaceReactionMaterial::reactionProgress(const PhysicsReactionDatabase::Reaction & reaction,
                                             const SpaceArg & r,
                                             const StateArg & state) const
{
  using std::sqrt;

  const auto & reactant_term = reaction.reactants.front();
  const auto & reactant = _database.species().at(reactant_term.species_index);

  const ADReal T = _temperature(r, state);
  const ADReal c = concentration(reactant_term.species_index, r, state);
  const ADReal mean_speed = sqrt(8.0 * PHYSICS_CONSTANTS::R * T / (PHYSICS_CONSTANTS::pi * reactant.molar_mass));

  const ADReal incident_molar_flux = 0.25 * c * mean_speed;

  return reaction.sticking * incident_molar_flux / reactant_term.coefficient;
}

template <typename SpaceArg, typename StateArg>
ADReal
PhysicsSurfaceReactionMaterial::outwardMassFlux(std::size_t database_species,
                                            const SpaceArg & r,
                                            const StateArg & state) const
{
  const auto & species = _database.species().at(database_species);
  if (species.kind != PhysicsReactionDatabase::SpeciesKind::Heavy)
    return ADReal(0.0);

  ADReal flux = 0.0;

  for (const auto reaction_index : _active_reactions)
  {
    const auto & reaction = _database.reactions().at(reaction_index);
    const auto nu = _database.stoichCoefficient(reaction, database_species);

    if (std::abs(nu) > 0.0)
      flux -= species.molar_mass * nu * reactionProgress(reaction, r, state);
  }

  return flux;
}
