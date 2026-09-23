#include "PhysicsFVCellFunctorNeumannBC.h"

registerMooseObject("PhysicsApp", PhysicsFVCellFunctorNeumannBC);

InputParameters
PhysicsFVCellFunctorNeumannBC::validParams()
{
  auto params = FVQpFluxBC::validParams();
  params.addClassDescription(
      "Neumann boundary condition that evaluates its flux functor on the adjacent FV cell "
      "instead of the boundary face. This is a generic realization adapter for closures "
      "that require cell-side state on a Dirichlet boundary.");
  params.addParam<MooseFunctorName>(
      "factor",
      1.0,
      "Functor-valued multiplier. Sign convention matches FVFunctorNeumannBC.");
  params.addRequiredParam<MooseFunctorName>(
      "functor", "Flux functor evaluated at the adjacent cell center.");
  return params;
}

PhysicsFVCellFunctorNeumannBC::PhysicsFVCellFunctorNeumannBC(
    const InputParameters & parameters)
  : FVQpFluxBC(parameters),
    _functor(getFunctor<ADReal>("functor")),
    _factor(getFunctor<ADReal>("factor"))
{
}

ADReal
PhysicsFVCellFunctorNeumannBC::computeQpResidual()
{
  const auto cell =
      _face_type == FaceInfo::VarFaceNeighbors::ELEM ? elemArg() : neighborArg();
  const auto state = determineState();
  return -_factor(cell, state) * _functor(cell, state);
}
