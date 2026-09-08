#pragma once

#include "FunctorMaterial.h"

/** Projects one canonical R_ion_O2 [mol/(m^3 s)] into particle sources. */
class QPXO2IonizationSourceMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  QPXO2IonizationSourceMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _reaction_progress;
  const Real _o2_molar_mass;
};
