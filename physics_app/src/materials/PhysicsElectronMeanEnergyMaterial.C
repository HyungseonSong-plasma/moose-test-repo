#include "PhysicsElectronMeanEnergyMaterial.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsElectronMeanEnergyMaterial);

InputParameters
PhysicsElectronMeanEnergyMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Builds mean electron energy from physical electron energy/number density, "
      "log-molar electron states, or the historical normalized electron states.");

  params.addParam<MooseEnum>(
      "state_form",
      MooseEnum("normalized physical_eV log_molar_eV", "normalized"),
      "State convention. physical_eV uses electron_energy_density [eV/m^3] and "
      "electron_density [1/m^3]. log_molar_eV uses their log-molar solved states.");

  params.addRequiredParam<MooseFunctorName>(
      "electron_energy_density",
      "Electron energy-density state; [eV/m^3] for physical_eV or log molar-energy state for log_molar_eV.");
  params.addRequiredParam<MooseFunctorName>(
      "electron_density",
      "Electron density state; [1/m^3] for physical_eV or log molar-density state for log_molar_eV.");

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
    _log_molar_state(getParam<MooseEnum>("state_form") == "log_molar_eV"),
    _electron_energy_density(getFunctor<ADReal>("electron_energy_density")),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _energy_reference_eV(
        isParamValid("energy_reference_eV") ? getParam<Real>("energy_reference_eV") : 1.0)
{
  if (!_physical_state && !_log_molar_state)
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
        const ADReal energy_state = _electron_energy_density(r, state);
        const ADReal density_state = _electron_density(r, state);

        ADReal mean_energy;
        if (_log_molar_state)
        {
          if (!std::isfinite(energy_state.value()) || !std::isfinite(density_state.value()))
            mooseError(
                "PhysicsElectronMeanEnergyMaterial requires finite log-molar electron states; got energy=",
                energy_state.value(),
                ", density=",
                density_state.value(),
                ".");

          using std::exp;
          mean_energy = exp(energy_state - density_state);
        }
        else
        {
          if (!std::isfinite(density_state.value()) || density_state.value() <= 0.0)
            mooseError(
                "PhysicsElectronMeanEnergyMaterial requires finite electron_density > 0; got ",
                density_state.value(),
                ".");

          if (!std::isfinite(energy_state.value()) || energy_state.value() < 0.0)
            mooseError(
                "PhysicsElectronMeanEnergyMaterial requires finite electron_energy_density >= 0; got ",
                energy_state.value(),
                ".");

          mean_energy =
              _physical_state
                  ? energy_state / density_state
                  : _energy_reference_eV * energy_state / density_state;
        }

        if (!std::isfinite(mean_energy.value()) || mean_energy.value() <= 0.0)
          mooseError(
              "PhysicsElectronMeanEnergyMaterial requires finite positive mean electron energy; got ",
              mean_energy.value(),
              " eV. No clamp is applied.");

        return mean_energy;
      });
}
