#pragma once

#include "FunctorMaterial.h"

/** Projects one canonical R_O2s [mol/(m^3 s)] into O2/O2s heavy-mass sources. */
class PhysicsO2sExcitationSourceMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsO2sExcitationSourceMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _reaction_progress;
  const Real _o2_molar_mass;
};
