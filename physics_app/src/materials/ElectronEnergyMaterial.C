#include "ElectronEnergyMaterial.h"

#include <cmath>

registerMooseObject("PhysicsApp", ElectronEnergyMaterial);

InputParameters
ElectronEnergyMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Builds the physical mean electron energy [eV] from physical or log-molar "
      "electron energy/density state Functors.");

  params.addParam<MooseEnum>(
      "state_form",
      MooseEnum("log_molar_eV physical_eV", "log_molar_eV"),
      "log_molar_eV: exp(log_molar_energy-log_molar_density) [eV]. "
      "physical_eV: physical energy density [eV/m^3] / electron number density [1/m^3].");

  params.addRequiredParam<MooseFunctorName>(
      "electron_energy_density",
      "Electron energy-density state; [eV/m^3] for physical_eV or log molar-energy state for log_molar_eV.");
  params.addRequiredParam<MooseFunctorName>(
      "electron_density",
      "Electron density state; [1/m^3] for physical_eV or log molar-density state for log_molar_eV.");

  return params;
}

ElectronEnergyMaterial::ElectronEnergyMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _log_molar_state(getParam<MooseEnum>("state_form") == "log_molar_eV"),
    _electron_energy_density(getFunctor<ADReal>("electron_energy_density")),
    _electron_density(getFunctor<ADReal>("electron_density"))
{
  addFunctorProperty<ADReal>(
      "e_energy_eV",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal energy_state = _electron_energy_density(r, state);
        const ADReal density_state = _electron_density(r, state);

        ADReal mean_energy;
        if (_log_molar_state)
        {
          if (!std::isfinite(energy_state.value()) || !std::isfinite(density_state.value()))
            mooseError(
                "ElectronEnergyMaterial requires finite log-molar electron states; got energy=",
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
                "ElectronEnergyMaterial requires finite electron_density > 0; got ",
                density_state.value(),
                ".");

          if (!std::isfinite(energy_state.value()) || energy_state.value() < 0.0)
            mooseError(
                "ElectronEnergyMaterial requires finite electron_energy_density >= 0; got ",
                energy_state.value(),
                ".");

          mean_energy = energy_state / density_state;
        }

        if (!std::isfinite(mean_energy.value()) || mean_energy.value() <= 0.0)
          mooseError(
              "ElectronEnergyMaterial requires finite positive mean electron energy; got ",
              mean_energy.value(),
              " eV. No clamp is applied.");

        return mean_energy;
      });
}
