#pragma once

#include "FunctorMaterial.h"
#include "Chemistry.h"

#include <map>
#include <string>
#include <vector>

/**
 * JSON ChemistryData neutral thermal-sticking surface reaction provider.
 * Produces canonical R_H* surface molar progress [mol/(m^2 s)] and signed
 * outward surface_mass_flux_* [kg/(m^2 s)]. Charged surface fluxes retain
 * their separate, explicit wall-transport owner.
 */
class SurfaceReactionMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  SurfaceReactionMaterial(const InputParameters & parameters);

protected:
  template <typename SpaceArg, typename StateArg>
  ADReal concentration(const std::string & species,
                       const SpaceArg & r,
                       const StateArg & state) const;

  template <typename SpaceArg, typename StateArg>
  ADReal reactionProgress(const Plasma::ReactionRecord & reaction,
                          const SpaceArg & r,
                          const StateArg & state) const;

  template <typename SpaceArg, typename StateArg>
  ADReal outwardMassFlux(const std::string & species,
                         const SpaceArg & r,
                         const StateArg & state) const;

  const Moose::Functor<ADReal> & _density;
  const Moose::Functor<ADReal> & _temperature;
  Plasma::ChemistryData _chemistry;
  std::map<std::string, const Moose::Functor<ADReal> *> _mass_fractions;
  std::vector<std::size_t> _active_reactions;
};
