#include "PhysicsFEMPlasmaTransport.h"
#include "MooseFunctorArguments.h"

registerMooseObject("PhysicsApp", PhysicsFEMPlasmaDriftDiffusion);
registerMooseObject("PhysicsApp", PhysicsFEMElectronJouleHeating);

InputParameters
PhysicsFEMPlasmaDriftDiffusion::validParams()
{
  auto params = ADKernel::validParams();
  params.addClassDescription(
      "Continuous-Galerkin electrostatic drift-diffusion for physical density-like states.");
  params.addRequiredCoupledVar("potential", "Electrostatic potential phi [V].");
  params.addRequiredParam<MooseFunctorName>("mobility", "Positive mobility [m^2/(V s)].");
  params.addRequiredParam<MooseFunctorName>("diffusion", "Diffusion coefficient [m^2/s].");
  params.addRequiredParam<Real>("charge_number", "Signed charge number z.");
  return params;
}

PhysicsFEMPlasmaDriftDiffusion::PhysicsFEMPlasmaDriftDiffusion(
    const InputParameters & parameters)
  : ADKernel(parameters),
    _grad_potential(adCoupledGradient("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _diffusion(getFunctor<ADReal>("diffusion")),
    _charge_number(getParam<Real>("charge_number"))
{
  if (_charge_number == 0.0)
    paramError("charge_number", "Drift-diffusion requires nonzero charge_number.");
}

ADReal
PhysicsFEMPlasmaDriftDiffusion::computeQpResidual()
{
  const Moose::ElemQpArg space_arg = {_current_elem, _qp, _qrule, _q_point[_qp]};
  const auto state = Moose::currentState();
  const ADReal mu = _mobility(space_arg, state);
  const ADReal D = _diffusion(space_arg, state);

  const ADRealVectorValue minus_flux =
      D * _grad_u[_qp] + _charge_number * mu * _u[_qp] * _grad_potential[_qp];

  return minus_flux * _grad_test[_i][_qp];
}

InputParameters
PhysicsFEMElectronJouleHeating::validParams()
{
  auto params = ADKernel::validParams();
  params.addClassDescription(
      "Adds +E.Gamma_e to a physical electron-energy residual, with E=-grad(phi)." );
  params.addRequiredCoupledVar("electron_density", "Physical electron number density [1/m^3].");
  params.addRequiredCoupledVar("potential", "Electrostatic potential phi [V].");
  params.addRequiredParam<MooseFunctorName>("mobility", "Electron mobility [m^2/(V s)].");
  params.addRequiredParam<MooseFunctorName>("diffusion", "Electron diffusion [m^2/s].");
  return params;
}

PhysicsFEMElectronJouleHeating::PhysicsFEMElectronJouleHeating(
    const InputParameters & parameters)
  : ADKernel(parameters),
    _electron_density(adCoupledValue("electron_density")),
    _grad_electron_density(adCoupledGradient("electron_density")),
    _grad_potential(adCoupledGradient("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _diffusion(getFunctor<ADReal>("diffusion"))
{
}

ADReal
PhysicsFEMElectronJouleHeating::computeQpResidual()
{
  const Moose::ElemQpArg space_arg = {_current_elem, _qp, _qrule, _q_point[_qp]};
  const auto state = Moose::currentState();
  const ADReal mu = _mobility(space_arg, state);
  const ADReal D = _diffusion(space_arg, state);

  const ADRealVectorValue electric_field = -_grad_potential[_qp];
  const ADRealVectorValue electron_flux =
      mu * _electron_density[_qp] * _grad_potential[_qp] -
      D * _grad_electron_density[_qp];

  return _test[_i][_qp] * (electric_field * electron_flux);
}
