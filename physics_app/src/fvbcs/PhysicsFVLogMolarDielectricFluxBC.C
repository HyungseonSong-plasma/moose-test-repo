#include "PhysicsFVLogMolarDielectricFluxBC.h"

#include "Physics.h"

registerMooseObject("PhysicsApp", PhysicsFVLogMolarDielectricFluxBC);

InputParameters
PhysicsFVLogMolarDielectricFluxBC::validParams()
{
  auto params = FVFluxBC::validParams();
  params.addClassDescription(
      "Applies a signed plasma-side particle-number flux on a plasma-dielectric interface to a "
      "log-molar FV species balance. Positive flux is outward from the species domain.");
  params.addRequiredParam<MooseFunctorName>(
      "signed_number_flux",
      "Signed particle-number flux [1/(m^2 s)]; positive outward from the plasma/species domain.");
  return params;
}

PhysicsFVLogMolarDielectricFluxBC::PhysicsFVLogMolarDielectricFluxBC(
    const InputParameters & parameters)
  : FVFluxBC(parameters),
    _signed_number_flux(getFunctor<ADReal>("signed_number_flux"))
{
}

ADReal
PhysicsFVLogMolarDielectricFluxBC::computeQpResidual()
{
  const auto face = singleSidedFaceArg();
  const ADReal gamma_signed = _signed_number_flux(face, determineState());
  return gamma_signed / PHYSICS_CONSTANTS::N_A;
}
