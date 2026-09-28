#include "PhysicsElectronMeanEnergyMaterial.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsElectronMeanEnergyMaterial);

InputParameters
PhysicsElectronMeanEnergyMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Builds mean electron energy from either physical electron energy/number density "
      "or the historical normalized electron states.");

  params.addParam<MooseEnum>(
      "state_form",
      MooseEnum("normalized physical_eV", "normalized"),
      "State convention. physical_eV uses electron_energy_density [eV/m^3] and "
      "electron_density [1/m^3].");

  params.addRequiredParam<MooseFunctorName>(
      "electron_energy_density",
      "Electron energy-density state; [eV/m^3] for state_form=physical_eV.");
  params.addRequiredParam<MooseFunctorName>(
      "electron_density",
      "Electron density state; [1/m^3] for state_form=physical_eV.");

  params.addParam<Real>(
      "energy_reference_eV",
      "Historical normalization energy epsilon_ref [eV]; required for state_form=normalized.");

  params.addParam<MooseFunctorName>(
      "mean_energy_output",
      "mean_en_solved",
      "Published mean-electron-energy functor [eV]. The default preserves legacy inputs.");

  return params;
}

PhysicsElectronMeanEnergyMaterial::PhysicsElectronMeanEnergyMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _physical_state(getParam<MooseEnum>("state_form") == "physical_eV"),
    _electron_energy_density(getFunctor<ADReal>("electron_energy_density")),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _energy_reference_eV(
        isParamValid("energy_reference_eV") ? getParam<Real>("energy_reference_eV") : 1.0)
{
  if (!_physical_state)
  {
    if (!isParamValid("energy_reference_eV"))
      paramError("energy_reference_eV",
                 "energy_reference_eV is required for state_form=normalized.");
    if (!std::isfinite(_energy_reference_eV) || _energy_reference_eV <= 0.0)
      paramError("energy_reference_eV",
                 "Electron-energy normalization scale must be finite and positive.");
  }

  addFunctorProperty<ADReal>(
      getParam<MooseFunctorName>("mean_energy_output"),
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal energy_density = _electron_energy_density(r, state);
        const ADReal electron_density = _electron_density(r, state);

        if (!std::isfinite(electron_density.value()) || electron_density.value() <= 0.0)
          mooseError(
              "PhysicsElectronMeanEnergyMaterial requires finite electron_density > 0; got ",
              electron_density.value(),
              ".");

        if (!std::isfinite(energy_density.value()) || energy_density.value() < 0.0)
          mooseError(
              "PhysicsElectronMeanEnergyMaterial requires finite electron_energy_density >= 0; got ",
              energy_density.value(),
              ".");

        const ADReal mean_energy =
            _physical_state
                ? energy_density / electron_density
                : _energy_reference_eV * energy_density / electron_density;

        if (!std::isfinite(mean_energy.value()))
          mooseError(
              "PhysicsElectronMeanEnergyMaterial requires finite mean electron energy; got ",
              mean_energy.value(),
              " eV. No clamp is applied.");

        return mean_energy;
      });
}
