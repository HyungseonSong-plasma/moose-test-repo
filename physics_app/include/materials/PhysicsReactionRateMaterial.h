#pragma once

#include "FunctorMaterial.h"
#include "PhysicsReactionDatabase.h"

#include <map>
#include <string>
#include <vector>

/**
 * Evaluates selected heavy-particle volume reactions from a chemistry database.
 *
 * Canonical internal reaction progress:
 *   R_r [mol/(m^3 s)]
 *
 * Heavy-species mass source:
 *   S_k = M_k * sum_r(nu_kr R_r) [kg/(m^3 s)]
 *
 * Species number source:
 *   Ndot_k = N_A * sum_r(nu_kr R_r) [1/(m^3 s)]
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

  template <typename SpaceArg, typename StateArg>
  ADReal molarSource(std::size_t database_species,
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
