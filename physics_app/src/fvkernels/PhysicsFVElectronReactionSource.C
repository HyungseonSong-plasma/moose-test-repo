#include "PhysicsFVElectronReactionSource.h"

registerMooseObject("PhysicsApp", PhysicsFVElectronReactionSource);

InputParameters
PhysicsFVElectronReactionSource::validParams()
{
  auto params = FVElementalKernel::validParams();

  params.addClassDescription(
      "Applies a signed physical electron reaction number source to physical n_e or the historical normalized n_e_hat equation.");

  params.addParam<MooseEnum>(
      "state_form", MooseEnum("normalized physical", "normalized"), "Electron density state convention.");

  params.addRequiredParam<MooseFunctorName>(
      "number_source",
      "Signed physical electron number source [1/(m^3 s)]. Positive means production.");

  params.addParam<Real>("n_ref", "Electron-density normalization n_ref [1/m^3]; required in normalized mode.");

  return params;
}

PhysicsFVElectronReactionSource::PhysicsFVElectronReactionSource(const InputParameters & parameters)
  : FVElementalKernel(parameters),
    _physical_state(getParam<MooseEnum>("state_form") == "physical"),
    _number_source(getFunctor<ADReal>("number_source")),
    _n_ref(isParamValid("n_ref") ? getParam<Real>("n_ref") : 1.0)
{
  if (!_physical_state)
  {
    if (!isParamValid("n_ref"))
      paramError("n_ref", "n_ref is required for state_form=normalized.");
    if (_n_ref <= 0.0)
      paramError("n_ref", "n_ref must be positive.");
  }
}

ADReal
PhysicsFVElectronReactionSource::computeQpResidual()
{
  const ADReal physical_number_source =
      _number_source(makeElemArg(_current_elem), determineState());

  return _physical_state ? -physical_number_source : -physical_number_source / _n_ref;
}
