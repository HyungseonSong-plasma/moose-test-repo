#include "PhysicsFVElectronEnergyJouleHeating.h"

#include "PhysicsElectronFluxModel.h"

registerMooseObject("PhysicsApp", PhysicsFVElectronEnergyJouleHeating);

InputParameters
PhysicsFVElectronEnergyJouleHeating::validParams()
{
  auto params = FVElementalKernel::validParams();

  params.addClassDescription(
      "Applies local electron-flux electric work -E.Gamma_e. physical_eV mode "
      "returns eV/(m^3 s); normalized mode preserves the historical scaled equation.");

  params.addParam<MooseEnum>(
      "state_form",
      MooseEnum("normalized physical_eV", "normalized"),
      "Electron-energy state convention.");

  params.addRequiredParam<MooseFunctorName>(
      "electron_density", "Electron density; use [1/m^3] for state_form=physical_eV.");
  params.addRequiredParam<MooseFunctorName>(
      "potential", "Electrostatic potential phi [V], with E = -grad(phi).");
  params.addRequiredParam<MooseFunctorName>(
      "mobility", "Canonical electron particle mobility mu_e [m^2/(V s)].");
  params.addRequiredParam<MooseFunctorName>(
      "diffusion", "Canonical electron particle diffusion coefficient D_e [m^2/s].");
  params.addParam<Real>(
      "energy_reference_eV",
      "Historical normalization energy epsilon_ref [eV]; required in normalized mode.");

  return params;
}

PhysicsFVElectronEnergyJouleHeating::PhysicsFVElectronEnergyJouleHeating(
    const InputParameters & parameters)
  : FVElementalKernel(parameters),
    _physical_state(getParam<MooseEnum>("state_form") == "physical_eV"),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _diffusion(getFunctor<ADReal>("diffusion")),
    _energy_reference_eV(
        isParamValid("energy_reference_eV") ? getParam<Real>("energy_reference_eV") : 1.0)
{
  if (!_physical_state)
  {
    if (!isParamValid("energy_reference_eV"))
      paramError("energy_reference_eV",
                 "energy_reference_eV is required for state_form=normalized.");
    if (_energy_reference_eV <= 0.0)
      paramError("energy_reference_eV",
                 "Electron-energy normalization scale must be positive.");
  }
}

ADReal
PhysicsFVElectronEnergyJouleHeating::computeQpResidual()
{
  const auto elem = makeElemArg(_current_elem);
  const auto state = determineState();

  const auto electric_field = -_potential.gradient(elem, state);
  const auto grad_electron_density = _electron_density.gradient(elem, state);
  const ADReal electron_density = _electron_density(elem, state);
  const ADReal mobility = _mobility(elem, state);
  const ADReal diffusion = _diffusion(elem, state);

  ADReal source =
      PhysicsElectronFluxModel::electronElectricWork(
          electron_density,
          grad_electron_density,
          electric_field,
          mobility,
          diffusion);

  if (!_physical_state)
    source /= _energy_reference_eV;

  return -source;
}
