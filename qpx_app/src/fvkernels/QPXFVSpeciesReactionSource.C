#include "QPXFVSpeciesReactionSource.h"

registerMooseObject("qpxApp", QPXFVSpeciesReactionSource);

InputParameters
QPXFVSpeciesReactionSource::validParams()
{
  auto params = FVElementalKernel::validParams();

  params.addClassDescription(
      "Applies a data-driven heavy-species reaction mass source to an FV equation.");

  params.addRequiredParam<MooseFunctorName>(
      "source",
      "Signed heavy-species mass source [kg/(m^3 s)]. Positive means production.");

  return params;
}

QPXFVSpeciesReactionSource::QPXFVSpeciesReactionSource(const InputParameters & parameters)
  : FVElementalKernel(parameters), _source(getFunctor<ADReal>("source"))
{
}

ADReal
QPXFVSpeciesReactionSource::computeQpResidual()
{
  return -_source(makeElemArg(_current_elem), determineState());
}
