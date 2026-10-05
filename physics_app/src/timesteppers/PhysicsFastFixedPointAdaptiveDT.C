#include "PhysicsFastFixedPointAdaptiveDT.h"

#include <algorithm>
#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFastFixedPointAdaptiveDT);

InputParameters
PhysicsFastFixedPointAdaptiveDT::validParams()
{
  auto params = TimeStepper::validParams();
  params.addClassDescription(
      "Adapts the physical timestep from predictor/corrector fast fixed-point iteration counts.");
  params.addRequiredParam<PostprocessorName>(
      "predictor_iterations", "Parent Receiver containing predictor fixed-point iterations.");
  params.addRequiredParam<PostprocessorName>(
      "corrector_iterations", "Parent Receiver containing corrector fixed-point iterations.");
  params.addRequiredRangeCheckedParam<Real>(
      "initial_dt", "initial_dt>0", "Initial physical timestep.");
  params.addRangeCheckedParam<Real>(
      "grow_factor", 1.5, "grow_factor>=1", "Multiplier when the fast blocks converge cheaply.");
  params.addRangeCheckedParam<Real>("shrink_factor",
                                    0.7,
                                    "shrink_factor>0 & shrink_factor<=1",
                                    "Multiplier when the fast blocks require many iterations.");
  params.addRangeCheckedParam<Real>("grow_below_iterations",
                                    8.0,
                                    "grow_below_iterations>=0",
                                    "Grow dt when max predictor/corrector iterations is below this.");
  params.addRangeCheckedParam<Real>(
      "shrink_above_iterations",
      8.0,
      "shrink_above_iterations>=0",
      "Shrink dt when max predictor/corrector iterations is above this.");
  return params;
}

PhysicsFastFixedPointAdaptiveDT::PhysicsFastFixedPointAdaptiveDT(
    const InputParameters & parameters)
  : TimeStepper(parameters),
    PostprocessorInterface(this),
    _predictor_iterations(getPostprocessorValue("predictor_iterations")),
    _corrector_iterations(getPostprocessorValue("corrector_iterations")),
    _initial_dt(getParam<Real>("initial_dt")),
    _grow_factor(getParam<Real>("grow_factor")),
    _shrink_factor(getParam<Real>("shrink_factor")),
    _grow_below_iterations(getParam<Real>("grow_below_iterations")),
    _shrink_above_iterations(getParam<Real>("shrink_above_iterations"))
{
  if (_grow_below_iterations > _shrink_above_iterations)
    paramError("grow_below_iterations",
               "grow_below_iterations must be <= shrink_above_iterations.");
}

Real
PhysicsFastFixedPointAdaptiveDT::computeInitialDT()
{
  return _initial_dt;
}

Real
PhysicsFastFixedPointAdaptiveDT::computeDT()
{
  if (!std::isfinite(_predictor_iterations) || !std::isfinite(_corrector_iterations))
    mooseError("Non-finite fast fixed-point iteration count: predictor=",
               _predictor_iterations,
               ", corrector=",
               _corrector_iterations);

  const Real max_iterations = std::max(_predictor_iterations, _corrector_iterations);

  Real requested_dt = _dt;
  const char * action = "hold";

  if (max_iterations < _grow_below_iterations)
  {
    requested_dt = _dt * _grow_factor;
    action = "grow";
  }
  else if (max_iterations > _shrink_above_iterations)
  {
    requested_dt = _dt * _shrink_factor;
    action = "shrink";
  }

  _console << "Fast fixed-point adaptive dt: predictor_its=" << _predictor_iterations
           << " corrector_its=" << _corrector_iterations << " max_its=" << max_iterations
           << " dt_old=" << _dt << " action=" << action << " dt_request=" << requested_dt
           << std::endl;

  return requested_dt;
}
