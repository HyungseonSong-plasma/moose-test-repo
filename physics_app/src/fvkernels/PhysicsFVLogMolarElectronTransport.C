#include "PhysicsFVLogMolarElectronTransport.h"

#include "PhysicsElectronFluxModel.h"
#include "RelationshipManager.h"

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

  return PhysicsElectronFluxModel::orthogonalDiffusiveFlux(
      coeff_face, c_elem, c_neighbor, _face_info->dCNMag());
}

InputParameters
PhysicsFVLogMolarElectrostaticDrift::validParams()
{
  auto params = PhysicsFVElectrostaticDrift::validParams();
  params.addClassDescription(
      "Compatibility alias for PhysicsFVElectrostaticDrift with "
      "transported_state=exponential. New inputs should use the canonical object directly.");
  params.set<MooseEnum>("transported_state") = "exponential";
  return params;
}

PhysicsFVLogMolarElectrostaticDrift::PhysicsFVLogMolarElectrostaticDrift(
    const InputParameters & parameters)
  : PhysicsFVElectrostaticDrift(parameters)
{
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
