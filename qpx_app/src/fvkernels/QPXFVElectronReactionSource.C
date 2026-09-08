#include "QPXFVElectronReactionSource.h"

registerMooseObject("qpxApp", QPXFVElectronReactionSource);

InputParameters
QPXFVElectronReactionSource::validParams()
{
  auto params = FVElementalKernel::validParams();

  params.addClassDescription(
      "Applies a signed physical electron reaction number source to the normalized n_e_hat equation.");

  params.addRequiredParam<MooseFunctorName>(
      "number_source",
      "Signed physical electron number source [1/(m^3 s)]. Positive means production.");

  params.addRequiredRangeCheckedParam<Real>(
      "n_ref", "n_ref > 0", "Electron-density normalization n_ref [1/m^3].");

  return params;
}

QPXFVElectronReactionSource::QPXFVElectronReactionSource(const InputParameters & parameters)
  : FVElementalKernel(parameters),
    _number_source(getFunctor<ADReal>("number_source")),
    _n_ref(getParam<Real>("n_ref"))
{
}

ADReal
QPXFVElectronReactionSource::computeQpResidual()
{
  const ADReal physical_number_source =
      _number_source(makeElemArg(_current_elem), determineState());

  return -physical_number_source / _n_ref;
}
