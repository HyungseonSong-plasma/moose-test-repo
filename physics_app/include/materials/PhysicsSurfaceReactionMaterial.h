#pragma once

#include "FunctorMaterial.h"
#include "PhysicsReactionDatabase.h"

#include <map>
#include <string>
#include <vector>

/**
 * Evaluates neutral thermal-sticking surface reactions from a chemistry database.
 *
 * Surface reaction progress:
 *   R_s [mol/(m^2 s)]
 *
 * Species surface mass flux:
 *   J_k,out = -M_k * sum_r(nu_kr R_s) [kg/(m^2 s)]
 *
 * Positive output is outward from the plasma. Negative output is inward.
 */
class PhysicsSurfaceReactionMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsSurfaceReactionMaterial(const InputParameters & parameters);

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
  ADReal outwardMassFlux(std::size_t database_species,
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
