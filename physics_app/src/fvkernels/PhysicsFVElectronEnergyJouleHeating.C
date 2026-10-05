#include "PhysicsFVElectronEnergyJouleHeating.h"

#include "PhysicsElectronFluxModel.h"

registerMooseObject("PhysicsApp", PhysicsFVElectronEnergyJouleHeating);

InputParameters
PhysicsFVElectronEnergyJouleHeating::validParams()
{
  auto params = FVElementalKernel::validParams();

  params.addClassDescription(
      "Adds +E.Gamma_e to the electron-energy residual, corresponding to the physical "
      "electron heating source -E.Gamma_e on the right-hand side. physical_eV mode "
      "uses electron density [1/m^3] and residual units eV/(m^3 s); molar_eV mode uses "
      "electron concentration [mol/m^3] and residual units eV mol/(m^3 s); normalized "
      "mode preserves the historical scaled equation. The optional one-timestep lag "
      "evaluates the complete Joule constitutive state at the previous physical time "
      "while retaining the Joule source in the transient energy balance.");

  params.addParam<MooseEnum>(
      "state_form",
      MooseEnum("normalized physical_eV molar_eV", "normalized"),
      "Electron-energy state convention.");

  params.addRequiredParam<MooseFunctorName>(
      "electron_density",
      "Electron density/concentration. Use [1/m^3] for state_form=physical_eV and "
      "[mol/m^3] for state_form=molar_eV.");
  params.addRequiredParam<MooseFunctorName>(
      "potential", "Electrostatic potential phi [V], with E = -grad(phi).");
  params.addRequiredParam<MooseFunctorName>(
      "mobility", "Canonical electron particle mobility mu_e [m^2/(V s)].");
  params.addRequiredParam<MooseFunctorName>(
      "diffusion", "Canonical electron particle diffusion coefficient D_e [m^2/s].");
  params.addParam<Real>(
      "energy_reference_eV",
      "Historical normalization energy epsilon_ref [eV]; required in normalized mode.");
  params.addParam<bool>(
      "lag_one_timestep",
      false,
      "Evaluate n_e, grad(n_e), phi, mobility and diffusion at the previous physical "
      "time state. This is a first-order semi-implicit stabilization of the Joule source.");

  return params;
}

PhysicsFVElectronEnergyJouleHeating::PhysicsFVElectronEnergyJouleHeating(
    const InputParameters & parameters)
  : FVElementalKernel(parameters),
    _normalized_state(getParam<MooseEnum>("state_form") == "normalized"),
    _lag_one_timestep(getParam<bool>("lag_one_timestep")),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _diffusion(getFunctor<ADReal>("diffusion")),
    _energy_reference_eV(
        isParamValid("energy_reference_eV") ? getParam<Real>("energy_reference_eV") : 1.0)
{
  if (_normalized_state)
  {
    if (!isParamValid("energy_reference_eV"))
      paramError("energy_reference_eV",
                 "energy_reference_eV is required for state_form=normalized.");
    if (_energy_reference_eV <= 0.0)
      paramError("energy_reference_eV",
                 "Electron-energy normalization scale must be positive.");
  }

  if (_lag_one_timestep && !_subproblem.isTransient())
    paramError("lag_one_timestep", "One-timestep Joule lag requires a transient problem.");
}

ADReal
PhysicsFVElectronEnergyJouleHeating::computeQpResidual()
{
  const auto elem = makeElemArg(_current_elem);
  const auto state = _lag_one_timestep
                         ? Moose::StateArg(1, Moose::SolutionIterationType::Time)
                         : determineState();

  const auto electric_field = -_potential.gradient(elem, state);
  const auto grad_electron_density = _electron_density.gradient(elem, state);
  const ADReal electron_density = _electron_density(elem, state);
  const ADReal mobility = _mobility(elem, state);
  const ADReal diffusion = _diffusion(elem, state);

  ADReal residual_work =
      PhysicsElectronFluxModel::electronElectricWork(
          electron_density,
          grad_electron_density,
          electric_field,
          mobility,
          diffusion);

  if (_normalized_state)
    residual_work /= _energy_reference_eV;

  // Physical electron heating is Q_e = -E.Gamma_e on the RHS, so the residual
  // contribution for d(w_e)/dt + div(Gamma_eps) - Q_e = 0 is +E.Gamma_e.
  return residual_work;
}
