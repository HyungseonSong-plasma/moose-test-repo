#pragma once

#include "FunctorMaterial.h"

/**
 * Controlled transition from existing arbitrary Functor provider names to
 * species_id + "_mobility"/"_diffusivity". Adds no equation or coefficient
 * model and does not modify the upstream provider or its numerical value.
 *
 * Use only when a producer does not yet expose canonical names. Do not
 * instantiate simultaneously with a direct canonical producer for a species.
 */
class PhysicsSpeciesTransportAliasMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsSpeciesTransportAliasMaterial(const InputParameters & parameters);

private:
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _diffusivity;
};
