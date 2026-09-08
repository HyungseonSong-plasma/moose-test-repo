#include "PhysicsFVMassFractionTimeDerivative.h"

registerADMooseObject("PhysicsApp", PhysicsFVMassFractionTimeDerivative);

InputParameters
PhysicsFVMassFractionTimeDerivative::validParams()
{
  InputParameters params = FVTimeKernel::validParams();

  params.addClassDescription(
      "Density-weighted finite-volume time derivative for a species "
      "mass fraction: rho * d(w_k)/dt.");

  params.addRequiredParam<MooseFunctorName>(
      "rho",
      "Mixture density rho [kg/m^3].");

  return params;
}

PhysicsFVMassFractionTimeDerivative::PhysicsFVMassFractionTimeDerivative(
    const InputParameters & parameters)
  : FVTimeKernel(parameters),
    _rho(getFunctor<ADReal>("rho"))
{
}

ADReal
PhysicsFVMassFractionTimeDerivative::computeQpResidual()
{
  const auto state = determineState();

  const Moose::ElemArg elem_arg{_current_elem, false};
  
  const ADReal rho = _rho(elem_arg, state);

  return rho * _u_dot[_qp];
}