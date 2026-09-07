#include "QPXBackgroundDensity.h"
#include "QPX.h"

registerMooseObject("qpxApp", QPXBackgroundDensity);

InputParameters
QPXBackgroundDensity::validParams()
{
  InputParameters params = AuxKernel::validParams();
  params.addCoupledVar("T_gas", 300, "The background gas temperature in Kelvin.");
  params.addCoupledVar("p_gas", 1.01e5,
                       "The background gas pressure in Pascals (defaulted to 1 standard atmosphere).");
  params.addClassDescription("");
  return params;
}

QPXBackgroundDensity::QPXBackgroundDensity(const InputParameters & parameters)
  : AuxKernel(parameters),
  _T_gas(coupledValue("T_gas")),
  _p_gas(coupledValue("p_gas"))
{
}

Real
QPXBackgroundDensity::computeValue()
{
  return std::log(_p_gas[_qp] / (QPX_CONSTANTS::k_boltz * _T_gas[_qp]) 
                  / QPX_CONSTANTS::N_A);
}
