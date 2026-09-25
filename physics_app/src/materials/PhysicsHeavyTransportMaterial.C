#include "PhysicsHeavyTransportMaterial.h"

registerMooseObject("PhysicsApp", PhysicsHeavyTransportMaterial);

InputParameters
PhysicsHeavyTransportMaterial::validParams()
{
  auto params = PhysicsThermalDiffusionMaterial::validParams();
  params.addClassDescription(
      "Multi-species heavy-particle transport closure providing mixture-averaged "
      "diffusion, thermal diffusion, and charged-particle collision transport.");
  return params;
}

PhysicsHeavyTransportMaterial::PhysicsHeavyTransportMaterial(
    const InputParameters & parameters)
  : PhysicsThermalDiffusionMaterial(parameters)
{
}
