#include "PhysicsFVElectrostaticDrift.h"

#include "FEProblemBase.h"
#include "PhysicsElectronFluxModel.h"
#include "RelationshipManager.h"
#include "metaphysicl/raw_type.h"

registerMooseObject("PhysicsApp", PhysicsFVElectrostaticDrift);

InputParameters
PhysicsFVElectrostaticDrift::validParams()
{
  auto params = FVFluxKernel::validParams();

  params.addClassDescription(
      "Finite-volume electrostatic drift flux using E = -grad(phi), "
      "framework-consistent FV advection interpolation, and either identity "
      "or exponential reconstruction of the solved state.");

  params.addRequiredParam<MooseFunctorName>(
      "potential", "Electrostatic potential phi [V].");

  params.addRequiredParam<MooseFunctorName>(
      "mobility", "Positive species mobility magnitude [m^2/(V s)].");

  params.addRequiredParam<MooseFunctorName>(
      "carrier",
      "Multiplicative carrier/conversion functor. Use rho for a heavy-species "
      "mass-fraction equation and 1 for a number-density or molar-density equation.");

  params.addRequiredParam<Real>(
      "charge_number", "Signed integer-like charge number z.");

  params.addParam<MooseEnum>(
      "transported_state",
      MooseEnum("identity exponential", "identity"),
      "How the physical transported scalar is reconstructed from the solved variable. "
      "Use exponential for a solved log-density/log-concentration state.");

  params += Moose::FV::advectedInterpolationParameter();

  params.addRelationshipManager(
      "ElementSideNeighborLayers",
      Moose::RelationshipManagerType::GEOMETRIC |
          Moose::RelationshipManagerType::ALGEBRAIC |
          Moose::RelationshipManagerType::COUPLING,
      [](const InputParameters & obj_params, InputParameters & rm_params)
      {
        FVRelationshipManagerInterface::setRMParamsAdvection(
            obj_params, rm_params, 2);
      });

  return params;
}

PhysicsFVElectrostaticDrift::PhysicsFVElectrostaticDrift(
    const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _carrier(getFunctor<ADReal>("carrier")),
    _charge_number(getParam<Real>("charge_number")),
    _exponential_state(getParam<MooseEnum>("transported_state") == "exponential")
{
  if (_charge_number == 0.0)
    paramError(
        "charge_number",
        "Electrostatic drift requires nonzero charge_number.");

  const bool need_more_ghosting =
      Moose::FV::setInterpolationMethod(
          *this, _advected_interp_method, "advected_interp_method");

  if (need_more_ghosting && _tid == 0)
    getCheckedPointerParam<FEProblemBase *>("_fe_problem_base")
        ->setErrorOnJacobianNonzeroReallocation(false);
}

ADReal
PhysicsFVElectrostaticDrift::computeQpResidual()
{
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

  const ADRealVectorValue electric_field =
      -_potential.gradient(centered_face, state);

  const ADReal mobility_face = _mobility(centered_face, state);
  const ADReal carrier_face = _carrier(centered_face, state);

  const ADReal drift_normal =
      PhysicsElectronFluxModel::driftNormal(
          _charge_number, mobility_face, electric_field, _normal);

  const bool elem_is_upwind =
      MetaPhysicL::raw_value(drift_normal) >= 0.0;

  const auto transported_face =
      makeFace(*_face_info,
               Moose::FV::limiterType(_advected_interp_method),
               elem_is_upwind,
               false,
               &limiter_time);

  const ADReal transported_value =
      PhysicsElectronFluxModel::transportedState(
          _var(transported_face, state), _exponential_state);

  return carrier_face * transported_value * drift_normal;
}
