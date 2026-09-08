#include "PhysicsFVElectronEnergyWallFluxBC.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFVElectronEnergyWallFluxBC);

InputParameters
PhysicsFVElectronEnergyWallFluxBC::validParams()
{
  auto params = FVFluxBC::validParams();

  params.addClassDescription(
      "Applies the frozen #26 E4-E5 outward electron-energy wall flux: "
      "(5/6) v_e,th n_eps_hat - (4 eV / epsilon_ref) Gamma_e,SEE_hat.");

  params.addRequiredParam<MooseFunctorName>(
      "electron_energy_density",
      "Normalized electron-energy density n_epsilon_hat used by the energy equation.");
  params.addRequiredParam<MooseFunctorName>(
      "mean_electron_energy", "Electron mean energy [eV] used for the thermal mean speed.");
  params.addRequiredParam<MooseFunctorName>(
      "see_number_flux",
      "Normalized inward secondary-electron particle flux Gamma_e,SEE/n_ref [m/s]. "
      "Gamma and ion-incidence semantics remain owned by the #27 A8 particle-wall path.");
  params.addRequiredParam<Real>(
      "energy_reference_eV",
      "Positive electron-energy normalization scale epsilon_ref [eV].");

  return params;
}

PhysicsFVElectronEnergyWallFluxBC::PhysicsFVElectronEnergyWallFluxBC(
    const InputParameters & parameters)
  : FVFluxBC(parameters),
    _electron_energy_density(getFunctor<ADReal>("electron_energy_density")),
    _mean_electron_energy(getFunctor<ADReal>("mean_electron_energy")),
    _see_number_flux(getFunctor<ADReal>("see_number_flux")),
    _energy_reference_eV(getParam<Real>("energy_reference_eV"))
{
  if (_energy_reference_eV <= 0.0)
    paramError("energy_reference_eV", "Electron-energy normalization scale must be positive.");
}

ADReal
PhysicsFVElectronEnergyWallFluxBC::computeQpResidual()
{
  using std::sqrt;

  const auto face = singleSidedFaceArg();
  const auto state = determineState();

  const ADReal electron_energy_density = _electron_energy_density(face, state);
  const ADReal mean_electron_energy = _mean_electron_energy(face, state);
  const ADReal see_number_flux = _see_number_flux(face, state);

  constexpr Real elementary_charge = 1.602176634e-19;
  constexpr Real electron_mass = 9.1093837139e-31;
  constexpr Real pi = 3.141592653589793238462643383279502884;
  constexpr Real see_energy_eV = 4.0;

  // This is the same thermal mean-speed definition used by the existing wall
  // helper, but intentionally not its 0.25*n_e*v absorbingNumberFlux contract.
  const ADReal mean_speed =
      sqrt(8.0 * elementary_charge * mean_electron_energy / (3.0 * pi * electron_mass));

  // Positive flux is outward loss.  The SEE term is inward, hence the minus.
  const ADReal thermal_energy_flux = (5.0 / 6.0) * mean_speed * electron_energy_density;
  const ADReal see_energy_flux = (see_energy_eV / _energy_reference_eV) * see_number_flux;

  return thermal_energy_flux - see_energy_flux;
}
