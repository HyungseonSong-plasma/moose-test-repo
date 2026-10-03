#include "PhysicsTemporalPotentialPredictor.h"

#include "Executioner.h"
#include "FixedPointSolve.h"

registerMooseObject("PhysicsApp", PhysicsTemporalPotentialPredictor);

InputParameters
PhysicsTemporalPotentialPredictor::validParams()
{
  InputParameters params = AuxKernel::validParams();
  params.addRangeCheckedParam<Real>(
      "alpha", 1.0, "alpha>=0 & alpha<=2", "Temporal extrapolation factor.");
  params.addRangeCheckedParam<unsigned int>(
      "start_step", 3, "start_step>=2", "First time step on which extrapolation is applied.");
  params.addClassDescription(
      "Initializes an auxiliary field at TIMESTEP_BEGIN using a linear predictor "
      "u_old + alpha * (u_old - u_older).");
  return params;
}

PhysicsTemporalPotentialPredictor::PhysicsTemporalPotentialPredictor(
    const InputParameters & parameters)
  : AuxKernel(parameters),
    _u_old(uOld()),
    _u_older(uOlder()),
    _alpha(getParam<Real>("alpha")),
    _start_step(getParam<unsigned int>("start_step"))
{
}

Real
PhysicsTemporalPotentialPredictor::computeValue()
{
  // TIMESTEP_BEGIN is revisited by every outer fixed-point iteration.
  // Apply the temporal extrapolation only on the first iteration of the
  // physical time step; afterwards preserve the current accelerated iterate.
  auto * const executioner = _app.getExecutioner();
  const bool first_fixed_point_iteration =
      executioner && executioner->hasSolveObject<FixedPointSolve>() &&
      executioner->fixedPointSolve().hasFixedPointIteration() &&
      executioner->fixedPointSolve().numFixedPointIts() == 1;

  if (_t_step < static_cast<int>(_start_step) || !first_fixed_point_iteration)
    return _u[_qp];

  return _u_old[_qp] + _alpha * (_u_old[_qp] - _u_older[_qp]);
}
