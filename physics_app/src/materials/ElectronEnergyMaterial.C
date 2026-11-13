#include "ElectronEnergyMaterial.h"

#include <cmath>

registerMooseObject("PhysicsApp", ElectronEnergyMaterial);

InputParameters
ElectronEnergyMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Builds mean electron energy [eV] from the log-molar electron "
      "energy and density solver-state Functors.");

  params.addParam<MooseEnum>(
      "state_form",
      MooseEnum("log_molar_eV", "log_molar_eV"),
      "The sole supported state representation is log_molar_eV: "
      "exp(log_molar_energy-log_molar_density) [eV].");

  params.addRequiredParam<MooseFunctorName>(
      "electron_energy_density",
      "Solved log-molar electron energy state log_e_energy [ln(eV mol/m^3)].");
  params.addRequiredParam<MooseFunctorName>(
      "electron_density",
      "Solved log-molar electron density state log_e [ln(mol/m^3)].");

  return params;
}

ElectronEnergyMaterial::ElectronEnergyMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _electron_energy_density(getFunctor<ADReal>("electron_energy_density")),
    _electron_density(getFunctor<ADReal>("electron_density"))
{
  addFunctorProperty<ADReal>(
      "e_energy_eV",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal energy_state = _electron_energy_density(r, state);
        const ADReal density_state = _electron_density(r, state);

        if (!std::isfinite(energy_state.value()) || !std::isfinite(density_state.value()))
          mooseError(
              "ElectronEnergyMaterial requires finite log-molar electron states; got energy=",
              energy_state.value(),
              ", density=",
              density_state.value(),
              ".");

        using std::exp;
        const ADReal mean_energy = exp(energy_state - density_state);

        if (!std::isfinite(mean_energy.value()) || mean_energy.value() <= 0.0)
          mooseError(
              "ElectronEnergyMaterial requires finite positive mean electron energy; got ",
              mean_energy.value(),
              " eV. No clamp is applied.");

        return mean_energy;
      });
}
