#include "QPXKelvinToeV.h"
#include "QPX.h"

registerMooseObject("qpxApp", QPXKelvinToeV);

InputParameters
QPXKelvinToeV::validParams()
{
  InputParameters params = AuxKernel::validParams();
  params.addParam<Real>("T_gas", 300, "The background gas temperature in Kelvin.");
  params.addClassDescription("");
  return params;
}

QPXKelvinToeV::QPXKelvinToeV(const InputParameters & parameters)
  : AuxKernel(parameters),
  _T_gas(getParam<Real>("T_gas"))
{
}

Real
QPXKelvinToeV::computeValue()
{
  return _T_gas / 11604.5;
}
