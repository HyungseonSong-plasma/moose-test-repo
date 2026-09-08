#pragma once

#include "PhysicsFVMassFractionAdvection.h"

registerADMooseObject("PhysicsApp", PhysicsFVMassFractionAdvection);

InputParameters
PhysicsFVMassFractionAdvection::validParams()
{
  InputParameters params = INSFVScalarFieldAdvection::validParams();

  params.addClassDescription(
      "Density-weighted finite-volume advection for a species mass fraction.");

  params.addRequiredParam<MooseFunctorName>(
      "rho",
      "Mixture density rho [kg/m^3].");

  return params;
}

PhysicsFVMassFractionAdvection::PhysicsFVMassFractionAdvection(
    const InputParameters & parameters)
  : INSFVScalarFieldAdvection(parameters),
    _rho(getFunctor<ADReal>("rho"))
{
}

ADReal
PhysicsFVMassFractionAdvection::computeQpResidual()
{
  const auto state = determineState();

  const auto & limiter_time =
      _subproblem.isTransient()
          ? Moose::StateArg(1, Moose::SolutionIterationType::Time)
          : Moose::StateArg(1, Moose::SolutionIterationType::Nonlinear);

  ADRealVectorValue advection_velocity;

  // ------------------------------------------------------------
  // Optional slip velocity
  // ------------------------------------------------------------
  if (_add_slip_model)
  {
    Moose::FaceArg face_arg;

    if (onBoundary(*_face_info))
      face_arg = singleSidedFaceArg();
    else
      face_arg =
          Moose::FaceArg{_face_info,
                         Moose::FV::LimiterType::CentralDifference,
                         true,
                         false,
                         nullptr,
                         &limiter_time};

    ADRealVectorValue slip_velocity;

    if (_dim >= 1)
      slip_velocity(0) = (*_u_slip)(face_arg, state);

    if (_dim >= 2)
      slip_velocity(1) = (*_v_slip)(face_arg, state);

    if (_dim >= 3)
      slip_velocity(2) = (*_w_slip)(face_arg, state);

    advection_velocity += slip_velocity;
  }

  // ------------------------------------------------------------
  // Bulk Rhie-Chow velocity
  // ------------------------------------------------------------

  const auto v = velocity();
  advection_velocity += v;

  // ------------------------------------------------------------
  // Interpolate species mass fraction to the face
  // ------------------------------------------------------------

  const auto face_arg =
      makeFace(*_face_info,
               limiterType(_advected_interp_method),
               MetaPhysicL::raw_value(v) * _normal > 0,
               false,
               &limiter_time);

  const auto w_face = _var(face_arg, state);

  // ------------------------------------------------------------
  // Evaluate density at the same face
  // ------------------------------------------------------------

  const auto rho_face = _rho(face_arg, state);

  // ------------------------------------------------------------
  // Density-weighted advective species flux
  //
  //   rho * (u . n) * w
  // ------------------------------------------------------------

  return rho_face *
         (_normal * advection_velocity) *
         w_face;
}