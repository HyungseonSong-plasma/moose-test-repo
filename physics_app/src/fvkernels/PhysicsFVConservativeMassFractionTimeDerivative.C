#include "PhysicsFVConservativeMassFractionTimeDerivative.h"

registerADMooseObject("PhysicsApp", PhysicsFVConservativeMassFractionTimeDerivative);

InputParameters
PhysicsFVConservativeMassFractionTimeDerivative::validParams()
{
  InputParameters params = FVTimeKernel::validParams();

  params.addClassDescription(
      "Backward-Euler conservative finite-volume accumulation for a species "
      "mass fraction: [rho^n w_k^n - rho^(n-1) w_k^(n-1)] / dt.");

  params.addRequiredParam<MooseFunctorName>(
      "rho",
      "Mixture density rho [kg/m^3]. Must be evaluable at current and old time states.");

  return params;
}

PhysicsFVConservativeMassFractionTimeDerivative::
PhysicsFVConservativeMassFractionTimeDerivative(const InputParameters & parameters)
  : FVTimeKernel(parameters),
    _rho(getFunctor<ADReal>("rho"))
{
}

ADReal
PhysicsFVConservativeMassFractionTimeDerivative::computeQpResidual()
{
  if (!_subproblem.isTransient())
    mooseError("PhysicsFVConservativeMassFractionTimeDerivative requires a transient problem.");

  if (_dt <= 0.0)
    mooseError("PhysicsFVConservativeMassFractionTimeDerivative requires dt > 0.");

  const auto state = determineState();
  const auto elem_arg = makeElemArg(_current_elem);

  const ADReal rho = _rho(elem_arg, state);
  const ADReal rho_old = _rho(elem_arg, Moose::oldState());

  const ADReal w = _var(elem_arg, state);
  const ADReal w_old = _var(elem_arg, Moose::oldState());

  return (rho * w - rho_old * w_old) / _dt;
}
