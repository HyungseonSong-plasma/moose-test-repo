#include "PhysicsFVTwoPointElectrostaticDriftControl.h"

#include "metaphysicl/raw_type.h"

registerMooseObject("PhysicsApp", PhysicsFVTwoPointElectrostaticDriftControl);

InputParameters
PhysicsFVTwoPointElectrostaticDriftControl::validParams()
{
  auto params = PhysicsFVElectrostaticDrift::validParams();
  params.addClassDescription(
      "Diagnostic-only Issue-228 electron-drift control using a two-cell, face-normal potential "
      "gradient instead of the corrected multidimensional FV gradient.");
  return params;
}

PhysicsFVTwoPointElectrostaticDriftControl::PhysicsFVTwoPointElectrostaticDriftControl(
    const InputParameters & parameters)
  : PhysicsFVElectrostaticDrift(parameters)
{
}

ADReal
PhysicsFVTwoPointElectrostaticDriftControl::computeQpResidual()
{
  // The production electron drift excludes all external physical boundaries,
  // so this diagnostic control is expected to execute only on internal faces.
  if (!_face_info || !_face_info->neighborPtr())
    return PhysicsFVElectrostaticDrift::computeQpResidual();

  const auto state = determineState();
  const auto & limiter_time =
      _subproblem.isTransient()
          ? Moose::StateArg(1, Moose::SolutionIterationType::Time)
          : Moose::StateArg(1, Moose::SolutionIterationType::Nonlinear);

  const auto centered_face =
      makeFace(*_face_info,
               Moose::FV::LimiterType::CentralDifference,
               true,
               false,
               &limiter_time);

  const ADReal mobility_face = _mobility(centered_face, state);
  const ADReal carrier_face = _carrier(centered_face, state);
  const ADReal phi_elem = _potential(elemArg(), state);
  const ADReal phi_neighbor = _potential(neighborArg(), state);

  const Real projection = _face_info->eCN() * _normal;
  const ADReal grad_phi_normal =
      (phi_neighbor - phi_elem) / _face_info->dCNMag() * projection;
  const ADReal electric_field_normal = -grad_phi_normal;
  const ADReal drift_normal = _charge_number * mobility_face * electric_field_normal;

  const bool elem_is_upwind = MetaPhysicL::raw_value(drift_normal) >= 0.0;
  const auto transported_face =
      makeFace(*_face_info,
               Moose::FV::limiterType(_advected_interp_method),
               elem_is_upwind,
               false,
               &limiter_time);
  const ADReal transported_value = _var(transported_face, state);

  return carrier_face * transported_value * drift_normal;
}
