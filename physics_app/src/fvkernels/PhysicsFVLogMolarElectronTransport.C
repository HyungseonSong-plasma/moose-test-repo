#include "PhysicsFVLogMolarElectronTransport.h"

#include "FEProblemBase.h"
#include "RelationshipManager.h"
#include "metaphysicl/raw_type.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectronTimeDerivative);
registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectronDiffusion);
registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectrostaticDrift);
registerMooseObject("PhysicsApp", PhysicsFVLogMolarElectronReactionSource);

namespace
{
constexpr Real avogadro_per_mol = 6.02214076e23;
}

InputParameters
PhysicsFVLogMolarElectronTimeDerivative::validParams()
{
  auto params = FVElementalKernel::validParams();
  params.addClassDescription(
      "Conservative backward-Euler molar balance reconstructed from c_e=exp(log_e) mol/m^3.");
  params.set<MultiMooseEnum>("vector_tags") = "time";
  params.set<MultiMooseEnum>("matrix_tags") = "system time";
  return params;
}

PhysicsFVLogMolarElectronTimeDerivative::PhysicsFVLogMolarElectronTimeDerivative(
    const InputParameters & parameters)
  : FVElementalKernel(parameters)
{
}

ADReal
PhysicsFVLogMolarElectronTimeDerivative::computeQpResidual()
{
  if (!_subproblem.isTransient())
    mooseError("PhysicsFVLogMolarElectronTimeDerivative requires transient execution.");
  if (_dt <= 0.0)
    mooseError("PhysicsFVLogMolarElectronTimeDerivative requires dt > 0.");

  using std::exp;
  const auto elem = makeElemArg(_current_elem);
  const ADReal log_c_new = _var(elem, determineState());
  const ADReal log_c_old = _var(elem, Moose::oldState());
  return (exp(log_c_new) - exp(log_c_old)) / _dt;
}

InputParameters
PhysicsFVLogMolarElectronDiffusion::validParams()
{
  auto params = FVFluxKernel::validParams();
  params += FVDiffusionInterpolationInterface::validParams();
  params.addClassDescription(
      "Orthogonal FV electron diffusion reconstructed from c_e=exp(log_e), returned in molar flux units.");
  params.addRequiredParam<MooseFunctorName>("coeff", "Electron diffusion coefficient [m^2/s].");
  MooseEnum coeff_interp_method("average harmonic", "harmonic");
  params.addParam<MooseEnum>(
      "coeff_interp_method", coeff_interp_method, "Face interpolation method for diffusivity.");
  params.set<unsigned short>("ghost_layers") = 2;
  params.addRelationshipManager(
      "ElementSideNeighborLayers",
      Moose::RelationshipManagerType::GEOMETRIC |
          Moose::RelationshipManagerType::ALGEBRAIC |
          Moose::RelationshipManagerType::COUPLING,
      [](const InputParameters & obj_params, InputParameters & rm_params)
      { FVRelationshipManagerInterface::setRMParamsDiffusion(obj_params, rm_params, 3); });
  return params;
}

PhysicsFVLogMolarElectronDiffusion::PhysicsFVLogMolarElectronDiffusion(
    const InputParameters & parameters)
  : FVFluxKernel(parameters),
    FVDiffusionInterpolationInterface(parameters),
    _coeff(getFunctor<ADReal>("coeff")),
    _coeff_interp_method(
        Moose::FV::selectInterpolationMethod(getParam<MooseEnum>("coeff_interp_method")))
{
}

ADReal
PhysicsFVLogMolarElectronDiffusion::computeQpResidual()
{
  using namespace Moose::FV;
  using std::exp;
  if (!_var.isInternalFace(*_face_info))
    return 0.0;

  const auto state = determineState();
  const ADReal coeff_elem = _coeff(elemArg(), state);
  const ADReal coeff_neighbor = _coeff(neighborArg(), state);
  if (!coeff_elem.value() && !coeff_neighbor.value())
    return 0.0;

  ADReal coeff_face;
  interpolate(_coeff_interp_method, coeff_face, coeff_elem, coeff_neighbor, *_face_info, true);

  const ADReal c_elem = exp(_var(elemArg(), state));
  const ADReal c_neighbor = exp(_var(neighborArg(), state));
  return -coeff_face * (c_neighbor - c_elem) / _face_info->dCNMag();
}

InputParameters
PhysicsFVLogMolarElectrostaticDrift::validParams()
{
  auto params = FVFluxKernel::validParams();
  params.addClassDescription(
      "Electrostatic FV drift reconstructed from c_e=exp(log_e), preserving "
      "PhysicsFVElectrostaticDrift face/upwind semantics and returning molar flux.");
  params.addRequiredParam<MooseFunctorName>("potential", "Electrostatic potential phi [V].");
  params.addRequiredParam<MooseFunctorName>("mobility", "Positive mobility magnitude [m^2/(V s)].");
  params.addRequiredParam<MooseFunctorName>(
      "carrier", "Multiplicative carrier functor; use 1 for electron molar concentration.");
  params.addRequiredParam<Real>("charge_number", "Signed charge number z.");
  params += Moose::FV::advectedInterpolationParameter();
  params.addRelationshipManager(
      "ElementSideNeighborLayers",
      Moose::RelationshipManagerType::GEOMETRIC |
          Moose::RelationshipManagerType::ALGEBRAIC |
          Moose::RelationshipManagerType::COUPLING,
      [](const InputParameters & obj_params, InputParameters & rm_params)
      { FVRelationshipManagerInterface::setRMParamsAdvection(obj_params, rm_params, 2); });
  return params;
}

PhysicsFVLogMolarElectrostaticDrift::PhysicsFVLogMolarElectrostaticDrift(
    const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _carrier(getFunctor<ADReal>("carrier")),
    _charge_number(getParam<Real>("charge_number"))
{
  if (_charge_number == 0.0)
    paramError("charge_number", "Electrostatic drift requires nonzero charge_number.");

  const bool need_more_ghosting =
      Moose::FV::setInterpolationMethod(*this, _advected_interp_method, "advected_interp_method");
  if (need_more_ghosting && _tid == 0)
    getCheckedPointerParam<FEProblemBase *>("_fe_problem_base")
        ->setErrorOnJacobianNonzeroReallocation(false);
}

ADReal
PhysicsFVLogMolarElectrostaticDrift::computeQpResidual()
{
  using std::exp;
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

  const ADRealVectorValue electric_field = -_potential.gradient(centered_face, state);
  const ADReal mobility_face = _mobility(centered_face, state);
  const ADReal carrier_face = _carrier(centered_face, state);
  const ADReal drift_normal =
      _charge_number * mobility_face * (electric_field * _normal);

  const bool elem_is_upwind = MetaPhysicL::raw_value(drift_normal) >= 0.0;
  const auto transported_face =
      makeFace(*_face_info,
               Moose::FV::limiterType(_advected_interp_method),
               elem_is_upwind,
               false,
               &limiter_time);

  const ADReal c_face = exp(_var(transported_face, state));
  return carrier_face * c_face * drift_normal;
}

InputParameters
PhysicsFVLogMolarElectronReactionSource::validParams()
{
  auto params = FVElementalKernel::validParams();
  params.addClassDescription(
      "Converts a signed physical electron number source to molar source for the log-molar equation.");
  params.addRequiredParam<MooseFunctorName>(
      "number_source", "Signed physical electron number source [1/(m^3 s)]. Positive is production.");
  return params;
}

PhysicsFVLogMolarElectronReactionSource::PhysicsFVLogMolarElectronReactionSource(
    const InputParameters & parameters)
  : FVElementalKernel(parameters), _number_source(getFunctor<ADReal>("number_source"))
{
}

ADReal
PhysicsFVLogMolarElectronReactionSource::computeQpResidual()
{
  const ADReal physical_number_source =
      _number_source(makeElemArg(_current_elem), determineState());
  return -physical_number_source / avogadro_per_mol;
}
