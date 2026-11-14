#pragma once

#include "FunctorMaterial.h"
#include "Chemistry.h"

#include <map>
#include <string>
#include <vector>

/**
 * Evaluate JSON ChemistryData heavy-particle volume rate laws.
 *
 * Each configured reaction publishes its canonical R_Hnn molar progress,
 * [mol/(m^3 s)], consumed unchanged by the Chemistry source projector.
 * Electron-impact progress belongs to its separate table provider.
 */
class HRateCoefMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  HRateCoefMaterial(const InputParameters & parameters);

protected:
  template <typename SpaceArg, typename StateArg>
  ADReal concentration(const std::string & species,
                       const SpaceArg & r,
                       const StateArg & state) const;

  template <typename SpaceArg, typename StateArg>
  ADReal reactionProgress(const Plasma::ReactionRecord & reaction,
                          const SpaceArg & r,
                          const StateArg & state) const;

  const Moose::Functor<ADReal> & _density;
  const Moose::Functor<ADReal> & _temperature;
  Plasma::ChemistryData _chemistry;

  std::map<std::string, const Moose::Functor<ADReal> *> _mass_fractions;
  std::vector<std::size_t> _active_reactions;
};
