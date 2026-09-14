#include "PhysicsFVLimitedElectrostaticDriftControl.h"

#include "metaphysicl/raw_type.h"

#include <algorithm>
#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFVLimitedElectrostaticDriftControl);

InputParameters
PhysicsFVLimitedElectrostaticDriftControl::validParams()
{
  auto params = PhysicsFVElectrostaticDrift::validParams();
  params.addClassDescription(
      "Diagnostic-only electron-drift control that bounds the non-orthogonal correction in "
      "the face-normal potential gradient relative to the two-point central term.");
  params.addRequiredRangeCheckedParam<Real>(
      "correction_cap_ratio",
      "correction_cap_ratio >= 0",
      "Maximum absolute non-orthogonal correction divided by the absolute central face-normal "
      "gradient contribution.");
  return params;
}

PhysicsFVLimitedElectrostaticDriftControl::PhysicsFVLimitedElectrostaticDriftControl(
    const InputParameters & parameters)
  : PhysicsFVElectrostaticDrift(parameters),
    _correction_cap_ratio(getParam<Real>("correction_cap_ratio"))
{
}

ADReal
PhysicsFVLimitedElectrostaticDriftControl::computeQpResidual()
{
  // Production electron drift excludes external physical boundaries. Fall back
  // to the parent implementation if this control is ever evaluated elsewhere.
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
  const ADReal central_grad_phi_normal =
      (phi_neighbor - phi_elem) / _face_info->dCNMag() * projection;

  const ADReal actual_grad_phi_normal = _potential.gradient(centered_face, state) * _normal;
  const ADReal correction = actual_grad_phi_normal - central_grad_phi_normal;

  const Real central_raw = MetaPhysicL::raw_value(central_grad_phi_normal);
  const Real correction_raw = MetaPhysicL::raw_value(correction);
  const Real correction_abs = std::abs(correction_raw);
  const Real cap = _correction_cap_ratio * std::abs(central_raw);
  const Real correction_scale =
      correction_abs > cap && correction_abs > 0.0 ? cap / correction_abs : 1.0;

  const ADReal limited_grad_phi_normal =
      central_grad_phi_normal + correction_scale * correction;
  const ADReal electric_field_normal = -limited_grad_phi_normal;
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
