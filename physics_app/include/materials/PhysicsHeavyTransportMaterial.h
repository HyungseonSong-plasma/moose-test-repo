#pragma once

#include "PhysicsThermalDiffusionMaterial.h"

/**
 * Semantic production name for the existing multi-species heavy transport
 * closure. The base implementation already owns mixture-averaged diffusion,
 * thermal diffusion, collision-integral data, and charged-charged transport.
 */
class PhysicsHeavyTransportMaterial : public PhysicsThermalDiffusionMaterial
{
public:
  static InputParameters validParams();
  PhysicsHeavyTransportMaterial(const InputParameters & parameters);
};
