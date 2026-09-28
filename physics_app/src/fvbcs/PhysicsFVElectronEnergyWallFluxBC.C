#include "PhysicsFVElectronEnergyWallFluxBC.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFVElectronEnergyWallFluxBC);

InputParameters
PhysicsFVElectronEnergyWallFluxBC::validParams()
{
  auto params = FVFluxBC::validParams();

  params.addClassDescription(
      "Applies the COMSOL-consistent outward electron-energy wall flux in either "
      "physical_eV or legacy normalized state.");

  params.addParam<MooseEnum>(
      "state_form",
      MooseEnum("normalized physical_eV", "normalized"),
      "Electron-energy state convention.");

  params.addRequiredParam<MooseFunctorName>(
      "electron_energy_density",
      "Electron energy density; use [eV/m^3] for state_form=physical_eV.");
  params.addRequiredParam<MooseFunctorName>(
      "mean_electron_energy", "Electron mean energy [eV] used for the thermal mean speed.");
  params.addRequiredParam<MooseFunctorName>(
      "see_number_flux",
      "Inward SEE particle-number flux; use [1/(m^2 s)] for state_form=physical_eV.");
  params.addParam<Real>(
      "energy_reference_eV",
      "Historical normalization energy epsilon_ref [eV]; required in normalized mode.");

  return params;
}

PhysicsFVElectronEnergyWallFluxBC::PhysicsFVElectronEnergyWallFluxBC(
    const InputParameters & parameters)
  : FVFluxBC(parameters),
    _physical_state(getParam<MooseEnum>("state_form") == "physical_eV"),
    _electron_energy_density(getFunctor<ADReal>("electron_energy_density")),
    _mean_electron_energy(getFunctor<ADReal>("mean_electron_energy")),
    _see_number_flux(getFunctor<ADReal>("see_number_flux")),
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

  // mean_electron_energy = (3/2) k_B T_e / e [eV], so the COMSOL
  // thermal mean speed sqrt(8 k_B T_e/(pi m_e)) is the expression below.
  const ADReal mean_speed =
      sqrt(16.0 * elementary_charge * mean_electron_energy / (3.0 * pi * electron_mass));

  // Positive flux is outward loss.  The SEE term is inward, hence the minus.
  const ADReal thermal_energy_flux = (5.0 / 6.0) * mean_speed * electron_energy_density;
  const ADReal see_energy_flux =
      _physical_state
          ? see_energy_eV * see_number_flux
          : (see_energy_eV / _energy_reference_eV) * see_number_flux;

  return thermal_energy_flux - see_energy_flux;
}
