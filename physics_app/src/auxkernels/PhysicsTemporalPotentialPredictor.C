#include "PhysicsTemporalPotentialPredictor.h"

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
  if (_t_step < static_cast<int>(_start_step))
    return _u_old[_qp];

  return _u_old[_qp] + _alpha * (_u_old[_qp] - _u_older[_qp]);
}
