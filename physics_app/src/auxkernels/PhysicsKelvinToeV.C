#include "PhysicsKelvinToeV.h"
#include "Physics.h"

registerMooseObject("PhysicsApp", PhysicsKelvinToeV);

InputParameters
PhysicsKelvinToeV::validParams()
{
  InputParameters params = AuxKernel::validParams();
  params.addParam<Real>("T_gas", 300, "The background gas temperature in Kelvin.");
  params.addClassDescription("");
  return params;
}

PhysicsKelvinToeV::PhysicsKelvinToeV(const InputParameters & parameters)
  : AuxKernel(parameters),
  _T_gas(getParam<Real>("T_gas"))
{
}

Real
PhysicsKelvinToeV::computeValue()
{
  return _T_gas / 11604.5;
}
