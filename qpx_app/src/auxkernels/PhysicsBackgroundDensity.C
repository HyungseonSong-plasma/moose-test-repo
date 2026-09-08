#include "PhysicsBackgroundDensity.h"
#include "Physics.h"

registerMooseObject("PhysicsApp", PhysicsBackgroundDensity);

InputParameters
PhysicsBackgroundDensity::validParams()
{
  InputParameters params = AuxKernel::validParams();
  params.addCoupledVar("T_gas", 300, "The background gas temperature in Kelvin.");
  params.addCoupledVar("p_gas", 1.01e5,
                       "The background gas pressure in Pascals (defaulted to 1 standard atmosphere).");
  params.addClassDescription("");
  return params;
}

PhysicsBackgroundDensity::PhysicsBackgroundDensity(const InputParameters & parameters)
  : AuxKernel(parameters),
  _T_gas(coupledValue("T_gas")),
  _p_gas(coupledValue("p_gas"))
{
}

Real
PhysicsBackgroundDensity::computeValue()
{
  return std::log(_p_gas[_qp] / (PHYSICS_CONSTANTS::k_boltz * _T_gas[_qp]) 
                  / PHYSICS_CONSTANTS::N_A);
}
