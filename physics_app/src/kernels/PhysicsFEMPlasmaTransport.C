#include "PhysicsFEMPlasmaTransport.h"
#include "MooseFunctorArguments.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFEMPlasmaDriftDiffusion);
registerMooseObject("PhysicsApp", PhysicsFEMElectronJouleHeating);
registerMooseObject("PhysicsApp", PhysicsFEMLogMolarTimeDerivative);
registerMooseObject("PhysicsApp", PhysicsFEMLogMolarDriftDiffusion);
registerMooseObject("PhysicsApp", PhysicsFEMLogMolarElectronJouleHeating);

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
      "Adds +E.Gamma_e to a physical electron-energy residual, with E=-grad(phi).");
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

InputParameters
PhysicsFEMLogMolarTimeDerivative::validParams()
{
  auto params = ADTimeKernel::validParams();
  params.addClassDescription(
      "Conservative backward-Euler time derivative of c=exp(u) for a FEM log-molar state.");
  return params;
}

PhysicsFEMLogMolarTimeDerivative::PhysicsFEMLogMolarTimeDerivative(
    const InputParameters & parameters)
  : ADTimeKernel(parameters), _u_old(_var.slnOld())
{
}

ADReal
PhysicsFEMLogMolarTimeDerivative::computeQpResidual()
{
  if (!_subproblem.isTransient())
    mooseError("PhysicsFEMLogMolarTimeDerivative requires transient execution.");
  if (_dt <= 0.0)
    mooseError("PhysicsFEMLogMolarTimeDerivative requires dt > 0.");

  using std::exp;
  return _test[_i][_qp] * (exp(_u[_qp]) - exp(_u_old[_qp])) / _dt;
}

InputParameters
PhysicsFEMLogMolarDriftDiffusion::validParams()
{
  auto params = ADKernel::validParams();
  params.addClassDescription(
      "Continuous-Galerkin electrostatic drift-diffusion reconstructed from c=exp(log_c).");
  params.addRequiredCoupledVar("potential", "Electrostatic potential phi [V].");
  params.addRequiredParam<MooseFunctorName>("mobility", "Positive mobility [m^2/(V s)].");
  params.addRequiredParam<MooseFunctorName>("diffusion", "Diffusion coefficient [m^2/s].");
  params.addRequiredParam<Real>("charge_number", "Signed charge number z.");
  return params;
}

PhysicsFEMLogMolarDriftDiffusion::PhysicsFEMLogMolarDriftDiffusion(
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
PhysicsFEMLogMolarDriftDiffusion::computeQpResidual()
{
  using std::exp;

  const Moose::ElemQpArg space_arg = {_current_elem, _qp, _qrule, _q_point[_qp]};
  const auto state = Moose::currentState();
  const ADReal mu = _mobility(space_arg, state);
  const ADReal D = _diffusion(space_arg, state);

  const ADReal c = exp(_u[_qp]);
  const ADRealVectorValue grad_c = c * _grad_u[_qp];
  const ADRealVectorValue minus_flux =
      D * grad_c + _charge_number * mu * c * _grad_potential[_qp];

  return minus_flux * _grad_test[_i][_qp];
}

InputParameters
PhysicsFEMLogMolarElectronJouleHeating::validParams()
{
  auto params = ADKernel::validParams();
  params.addClassDescription(
      "Adds +E.Gamma_e to the log-molar electron-energy residual, with E=-grad(phi).");
  params.addRequiredCoupledVar(
      "electron_log_density", "Solved log-molar electron concentration log(c_e).");
  params.addRequiredCoupledVar("potential", "Electrostatic potential phi [V].");
  params.addRequiredParam<MooseFunctorName>("mobility", "Electron mobility [m^2/(V s)].");
  params.addRequiredParam<MooseFunctorName>("diffusion", "Electron diffusion [m^2/s].");
  return params;
}

PhysicsFEMLogMolarElectronJouleHeating::PhysicsFEMLogMolarElectronJouleHeating(
    const InputParameters & parameters)
  : ADKernel(parameters),
    _log_electron_density(adCoupledValue("electron_log_density")),
    _grad_log_electron_density(adCoupledGradient("electron_log_density")),
    _grad_potential(adCoupledGradient("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _diffusion(getFunctor<ADReal>("diffusion"))
{
}

ADReal
PhysicsFEMLogMolarElectronJouleHeating::computeQpResidual()
{
  using std::exp;

  const Moose::ElemQpArg space_arg = {_current_elem, _qp, _qrule, _q_point[_qp]};
  const auto state = Moose::currentState();
  const ADReal mu = _mobility(space_arg, state);
  const ADReal D = _diffusion(space_arg, state);

  const ADReal c_e = exp(_log_electron_density[_qp]);
  const ADRealVectorValue grad_c_e = c_e * _grad_log_electron_density[_qp];
  const ADRealVectorValue electric_field = -_grad_potential[_qp];
  const ADRealVectorValue electron_flux =
      mu * c_e * _grad_potential[_qp] - D * grad_c_e;

  return _test[_i][_qp] * (electric_field * electron_flux);
}
