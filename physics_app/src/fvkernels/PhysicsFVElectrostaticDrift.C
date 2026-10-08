#include "PhysicsFVElectrostaticDrift.h"

#include "FEProblemBase.h"
#include "RelationshipManager.h"
#include "metaphysicl/raw_type.h"

registerMooseObject("PhysicsApp", PhysicsFVElectrostaticDrift);

InputParameters
PhysicsFVElectrostaticDrift::validParams()
{
  auto params = FVFluxKernel::validParams();

  params.addClassDescription(
      "Finite-volume electrostatic drift flux using E = -grad(phi) and "
      "framework-consistent FV advection interpolation. Mixed FE/FV systems "
      "may reconstruct the face electric field from adjacent element gradients.");

  params.addRequiredParam<MooseFunctorName>(
      "potential", "Electrostatic potential phi [V].");

  params.addRequiredParam<MooseFunctorName>(
      "mobility", "Positive species mobility magnitude [m^2/(V s)].");

  params.addRequiredParam<MooseFunctorName>(
      "carrier",
      "Multiplicative carrier/conversion functor. Use rho for a heavy-species "
      "mass-fraction equation and 1 for a number-density equation.");

  params.addRequiredParam<Real>(
      "charge_number", "Signed integer-like charge number z.");

  params.addParam<bool>(
      "freeze_upwind_direction_to_old_potential",
      false,
      "For transient nonlinear diagnostics, choose the upwind side from the previous "
      "physical-time potential while retaining the current nonlinear potential in the "
      "drift flux magnitude. This prevents stencil switching between Newton iterates.");

  params.addParam<bool>(
      "lag_advected_variable_to_old_time",
      false,
      "For transient nonlinear diagnostics, evaluate the transported scalar in the drift "
      "flux from the previous physical-time state while retaining the current nonlinear "
      "potential in the electric-field factor. This removes the n^{n+1}*grad(phi^{n+1}) "
      "bilinear product without making the electrostatic field explicit.");

  params.addParam<bool>(
      "use_element_gradient_for_potential",
      false,
      "Reconstruct E=-grad(phi) at an internal FV face by averaging the adjacent "
      "element gradients, and use the adjacent-element gradient at an external "
      "boundary. Enable this when potential is a continuous FEM variable, because "
      "continuous FEM functors do not implement FaceArg gradients.");

  // Match the framework FVAdvection interpolation contract.
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
    _freeze_upwind_direction_to_old_potential(
        getParam<bool>("freeze_upwind_direction_to_old_potential")),
    _lag_advected_variable_to_old_time(
        getParam<bool>("lag_advected_variable_to_old_time")),
    _use_element_gradient_for_potential(
        getParam<bool>("use_element_gradient_for_potential"))
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

  // FE functors do not implement FaceArg gradients.  For the mixed FE/FV
  // bridge evaluate grad(phi) in adjacent elements and interpolate that vector
  // to the face.  This keeps the field fully AD-coupled to the FEM potential.
  const auto electricField = [this, &centered_face](const auto & eval_state)
      -> ADRealVectorValue
  {
    if (!_use_element_gradient_for_potential)
      return -_potential.gradient(centered_face, eval_state);

    if (_var.isInternalFace(*_face_info))
    {
      const auto grad_elem = _potential.gradient(elemArg(), eval_state);
      const auto grad_neighbor = _potential.gradient(neighborArg(), eval_state);
      ADRealVectorValue grad_face;
      Moose::FV::interpolate(Moose::FV::InterpMethod::Average,
                             grad_face,
                             grad_elem,
                             grad_neighbor,
                             *_face_info,
                             true);
      return -grad_face;
    }

    return -_potential.gradient(elemArg(), eval_state);
  };

  const ADRealVectorValue electric_field = electricField(state);

  const ADReal mobility_face = _mobility(centered_face, state);
  const ADReal carrier_face = _carrier(centered_face, state);

  const ADReal drift_normal =
      _charge_number * mobility_face * (electric_field * _normal);

  bool elem_is_upwind;
  if (_freeze_upwind_direction_to_old_potential && _subproblem.isTransient())
  {
    const Moose::StateArg old_time_state(1, Moose::SolutionIterationType::Time);
    const ADRealVectorValue old_electric_field = electricField(old_time_state);
    const Real old_drift_direction =
        _charge_number * MetaPhysicL::raw_value(old_electric_field * _normal);
    elem_is_upwind = old_drift_direction >= 0.0;
  }
  else
    elem_is_upwind = MetaPhysicL::raw_value(drift_normal) >= 0.0;

  const auto transported_face =
      makeFace(*_face_info,
               Moose::FV::limiterType(_advected_interp_method),
               elem_is_upwind,
               false,
               &limiter_time);

  ADReal transported_value;
  if (_lag_advected_variable_to_old_time && _subproblem.isTransient())
  {
    const Moose::StateArg old_time_state(1, Moose::SolutionIterationType::Time);
    transported_value = _var(transported_face, old_time_state);
  }
  else
    transported_value = _var(transported_face, state);

  return carrier_face * transported_value * drift_normal;
}
