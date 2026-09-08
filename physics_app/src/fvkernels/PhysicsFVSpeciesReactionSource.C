#include "PhysicsFVSpeciesReactionSource.h"

registerMooseObject("PhysicsApp", PhysicsFVSpeciesReactionSource);

InputParameters
PhysicsFVSpeciesReactionSource::validParams()
{
  auto params = FVElementalKernel::validParams();

  params.addClassDescription(
      "Applies a data-driven heavy-species reaction mass source to an FV equation.");

  params.addRequiredParam<MooseFunctorName>(
      "source",
      "Signed heavy-species mass source [kg/(m^3 s)]. Positive means production.");

  return params;
}

PhysicsFVSpeciesReactionSource::PhysicsFVSpeciesReactionSource(const InputParameters & parameters)
  : FVElementalKernel(parameters), _source(getFunctor<ADReal>("source"))
{
}

ADReal
PhysicsFVSpeciesReactionSource::computeQpResidual()
{
  return -_source(makeElemArg(_current_elem), determineState());
}
