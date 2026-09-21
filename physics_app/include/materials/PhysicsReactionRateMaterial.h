#pragma once

#include "FunctorMaterial.h"
#include "PhysicsReactionDatabase.h"

#include <map>
#include <string>
#include <vector>

/**
 * Evaluates selected heavy-particle volume reactions from a chemistry database.
 *
 * Publishes one canonical reaction progress per active reaction:
 *   R_r [mol/(m^3 s)]
 *
 * Species/electron/energy source projections are owned downstream and must reuse
 * these canonical progress functors rather than re-evaluating the kinetic law.
 */
class PhysicsReactionRateMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsReactionRateMaterial(const InputParameters & parameters);

protected:
  template <typename SpaceArg, typename StateArg>
  ADReal concentration(std::size_t database_species,
                       const SpaceArg & r,
                       const StateArg & state) const;

  template <typename SpaceArg, typename StateArg>
  ADReal reactionProgress(const PhysicsReactionDatabase::Reaction & reaction,
                          const SpaceArg & r,
                          const StateArg & state) const;

  const Moose::Functor<ADReal> & _density;
  const Moose::Functor<ADReal> & _temperature;

  PhysicsReactionDatabase _database;

  std::vector<std::string> _active_species_names;
  std::vector<MooseFunctorName> _mass_fraction_names;
  std::map<std::size_t, const Moose::Functor<ADReal> *> _mass_fraction_by_database_species;

  std::vector<std::size_t> _active_reactions;
};
