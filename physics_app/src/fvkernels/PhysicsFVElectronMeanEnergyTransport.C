#include "PhysicsFVElectronMeanEnergyTransport.h"

#include "FEProblemBase.h"
#include "RelationshipManager.h"
#include "metaphysicl/raw_type.h"

registerADMooseObject("PhysicsApp", PhysicsFVElectronMeanEnergyTimeDerivative);
registerMooseObject("PhysicsApp", PhysicsFVElectronMeanEnergyDiffusion);
registerMooseObject("PhysicsApp", PhysicsFVElectronMeanEnergyElectrostaticDrift);

InputParameters
PhysicsFVElectronMeanEnergyTimeDerivative::validParams()
{
  auto params = FVTimeKernel::validParams();
  params.addClassDescription(
      "Conservative backward-Euler accumulation of physical electron energy density "
      "while mean_en [eV] is the solved variable.");
  params.addRequiredParam<MooseFunctorName>(
      "electron_density", "Physical electron number density n_e [1/m^3].");
  return params;
}

PhysicsFVElectronMeanEnergyTimeDerivative::PhysicsFVElectronMeanEnergyTimeDerivative(
    const InputParameters & parameters)
  : FVTimeKernel(parameters),
    _electron_density(getFunctor<ADReal>("electron_density"))
{
}

ADReal
PhysicsFVElectronMeanEnergyTimeDerivative::computeQpResidual()
{
  if (!_subproblem.isTransient())
    mooseError("PhysicsFVElectronMeanEnergyTimeDerivative requires transient execution.");
  if (_dt <= 0.0)
    mooseError("PhysicsFVElectronMeanEnergyTimeDerivative requires dt > 0.");

  const auto elem = makeElemArg(_current_elem);
  const auto state = determineState();

  const ADReal n_new = _electron_density(elem, state);
  const ADReal n_old = _electron_density(elem, Moose::oldState());
  const ADReal mean_new = _var(elem, state);
  const ADReal mean_old = _var(elem, Moose::oldState());

  return (n_new * mean_new - n_old * mean_old) / _dt;
}

InputParameters
PhysicsFVElectronMeanEnergyDiffusion::validParams()
{
  auto params = FVFluxKernel::validParams();
  params += FVDiffusionInterpolationInterface::validParams();

  params.addClassDescription(
      "Orthogonal FV diffusion of n_e*mean_en while mean_en [eV] is the solved variable.");
  params.addRequiredParam<MooseFunctorName>(
      "electron_density", "Physical electron number density n_e [1/m^3].");
  params.addRequiredParam<MooseFunctorName>(
      "coeff", "Electron-energy diffusion coefficient [m^2/s].");

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

PhysicsFVElectronMeanEnergyDiffusion::PhysicsFVElectronMeanEnergyDiffusion(
    const InputParameters & parameters)
  : FVFluxKernel(parameters),
    FVDiffusionInterpolationInterface(parameters),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _coeff(getFunctor<ADReal>("coeff")),
    _coeff_interp_method(
        Moose::FV::selectInterpolationMethod(getParam<MooseEnum>("coeff_interp_method")))
{
}

ADReal
PhysicsFVElectronMeanEnergyDiffusion::computeQpResidual()
{
  using namespace Moose::FV;

  if (!_var.isInternalFace(*_face_info))
    return 0.0;

  const auto state = determineState();

  const ADReal coeff_elem = _coeff(elemArg(), state);
  const ADReal coeff_neighbor = _coeff(neighborArg(), state);
  if (!coeff_elem.value() && !coeff_neighbor.value())
    return 0.0;

  ADReal coeff_face;
  interpolate(_coeff_interp_method,
              coeff_face,
              coeff_elem,
              coeff_neighbor,
              *_face_info,
              true);

  const ADReal energy_elem =
      _electron_density(elemArg(), state) * _var(elemArg(), state);
  const ADReal energy_neighbor =
      _electron_density(neighborArg(), state) * _var(neighborArg(), state);

  return -coeff_face * (energy_neighbor - energy_elem) / _face_info->dCNMag();
}

InputParameters
PhysicsFVElectronMeanEnergyElectrostaticDrift::validParams()
{
  auto params = FVFluxKernel::validParams();

  params.addClassDescription(
      "Electrostatic drift of n_e*mean_en while mean_en [eV] is the solved variable.");
  params.addRequiredParam<MooseFunctorName>(
      "electron_density", "Physical electron number density n_e [1/m^3].");
  params.addRequiredParam<MooseFunctorName>(
      "potential", "Electrostatic potential phi [V].");
  params.addRequiredParam<MooseFunctorName>(
      "mobility", "Positive electron-energy mobility magnitude [m^2/(V s)].");
  params.addRequiredParam<Real>(
      "charge_number", "Signed charge number z.");

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

PhysicsFVElectronMeanEnergyElectrostaticDrift::
PhysicsFVElectronMeanEnergyElectrostaticDrift(const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
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
PhysicsFVElectronMeanEnergyElectrostaticDrift::computeQpResidual()
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

  const ADRealVectorValue electric_field = -_potential.gradient(centered_face, state);
  const ADReal mobility_face = _mobility(centered_face, state);
  const ADReal drift_normal = _charge_number * mobility_face * (electric_field * _normal);

  const bool elem_is_upwind = MetaPhysicL::raw_value(drift_normal) >= 0.0;
  const auto transported_face =
      makeFace(*_face_info,
               Moose::FV::limiterType(_advected_interp_method),
               elem_is_upwind,
               false,
               &limiter_time);

  const ADReal energy_density_face =
      _electron_density(transported_face, state) * _var(transported_face, state);

  return energy_density_face * drift_normal;
}
