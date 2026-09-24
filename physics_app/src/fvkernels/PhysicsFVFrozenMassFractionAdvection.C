#include "PhysicsFVFrozenMassFractionAdvection.h"

registerADMooseObject("PhysicsApp", PhysicsFVFrozenMassFractionAdvection);

InputParameters
PhysicsFVFrozenMassFractionAdvection::validParams()
{
  InputParameters params = FVFluxKernel::validParams();
  params.addClassDescription(
      "Density-weighted FV species advection with prescribed read-only velocity for Issue331.");
  params.addRequiredParam<MooseFunctorName>("rho", "Frozen mixture density rho [kg/m^3].");
  params.addRequiredParam<MooseFunctorName>("velocity", "Frozen neutral-gas velocity [m/s].");
  Moose::FV::setInterpolationMethods(params);
  return params;
}

PhysicsFVFrozenMassFractionAdvection::PhysicsFVFrozenMassFractionAdvection(
    const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _rho(getFunctor<ADReal>("rho")),
    _velocity(getFunctor<ADRealVectorValue>("velocity")),
    _advected_interp_method(Moose::FV::selectInterpolationMethod(parameters))
{
}

ADReal
PhysicsFVFrozenMassFractionAdvection::computeQpResidual()
{
  const auto state = determineState();
  const auto & limiter_time =
      _subproblem.isTransient()
          ? Moose::StateArg(1, Moose::SolutionIterationType::Time)
          : Moose::StateArg(1, Moose::SolutionIterationType::Nonlinear);

  const Moose::FaceArg velocity_face{
      _face_info,
      Moose::FV::LimiterType::CentralDifference,
      true,
      false,
      nullptr,
      &limiter_time};
  const auto velocity = _velocity(velocity_face, state);

  const auto face_arg =
      makeFace(*_face_info,
               limiterType(_advected_interp_method),
               MetaPhysicL::raw_value(velocity) * _normal > 0,
               false,
               &limiter_time);

  const auto w_face = _var(face_arg, state);
  const auto rho_face = _rho(face_arg, state);

  return rho_face * (_normal * velocity) * w_face;
}
