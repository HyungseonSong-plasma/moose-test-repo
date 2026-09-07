#include "QPXFVElectronEnergyJouleHeating.h"

registerMooseObject("qpxApp", QPXFVElectronEnergyJouleHeating);

InputParameters
QPXFVElectronEnergyJouleHeating::validParams()
{
  auto params = FVElementalKernel::validParams();

  params.addClassDescription(
      "Applies the full local electron-flux electric-work source -E.Gamma_e to "
      "the normalized electron-energy equation using the canonical particle "
      "mobility and diffusion coefficients.");

  params.addRequiredParam<MooseFunctorName>(
      "electron_density", "Normalized electron density n_hat used by the particle equation.");
  params.addRequiredParam<MooseFunctorName>(
      "potential", "Electrostatic potential phi [V], with E = -grad(phi).");
  params.addRequiredParam<MooseFunctorName>(
      "mobility", "Canonical electron particle mobility mu_e [m^2/(V s)].");
  params.addRequiredParam<MooseFunctorName>(
      "diffusion", "Canonical electron particle diffusion coefficient D_e [m^2/s].");
  params.addRequiredParam<Real>(
      "energy_reference_eV",
      "Positive electron-energy normalization scale epsilon_ref [eV].");

  return params;
}

QPXFVElectronEnergyJouleHeating::QPXFVElectronEnergyJouleHeating(
    const InputParameters & parameters)
  : FVElementalKernel(parameters),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _potential(getFunctor<ADReal>("potential")),
    _mobility(getFunctor<ADReal>("mobility")),
    _diffusion(getFunctor<ADReal>("diffusion")),
    _energy_reference_eV(getParam<Real>("energy_reference_eV"))
{
  if (_energy_reference_eV <= 0.0)
    paramError("energy_reference_eV", "Electron-energy normalization scale must be positive.");
}

ADReal
QPXFVElectronEnergyJouleHeating::computeQpResidual()
{
  const auto elem = makeElemArg(_current_elem);
  const auto state = determineState();

  const auto electric_field = -_potential.gradient(elem, state);
  const auto grad_electron_density = _electron_density.gradient(elem, state);
  const ADReal electron_density = _electron_density(elem, state);
  const ADReal mobility = _mobility(elem, state);
  const ADReal diffusion = _diffusion(elem, state);

  // Gamma_e / n_ref = -mu_e*n_hat*E - D_e*grad(n_hat).
  // Therefore -E.Gamma_e/(n_ref*epsilon_ref) is the positive RHS source below.
  const ADReal normalized_source =
      (mobility * electron_density * (electric_field * electric_field) +
       diffusion * (electric_field * grad_electron_density)) /
      _energy_reference_eV;

  return -normalized_source;
}
