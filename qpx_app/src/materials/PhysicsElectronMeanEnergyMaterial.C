#include "PhysicsElectronMeanEnergyMaterial.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsElectronMeanEnergyMaterial);

InputParameters
PhysicsElectronMeanEnergyMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Builds mean_en_solved = epsilon_ref*n_epsilon_hat/n_e_hat from the "
      "normalized solved electron-energy and electron-density FV states.");

  params.addRequiredParam<MooseFunctorName>(
      "electron_energy_density",
      "Normalized conserved electron-energy density n_epsilon_hat.");

  params.addRequiredParam<MooseFunctorName>(
      "electron_density",
      "Normalized electron number density n_e_hat.");

  params.addRequiredParam<Real>(
      "energy_reference_eV",
      "Positive electron-energy normalization scale epsilon_ref [eV].");

  return params;
}

PhysicsElectronMeanEnergyMaterial::PhysicsElectronMeanEnergyMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _electron_energy_density(getFunctor<ADReal>("electron_energy_density")),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _energy_reference_eV(getParam<Real>("energy_reference_eV"))
{
  if (!std::isfinite(_energy_reference_eV) || _energy_reference_eV <= 0.0)
    paramError("energy_reference_eV", "Electron-energy normalization scale must be finite and positive.");

  addFunctorProperty<ADReal>(
      "mean_en_solved",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal n_epsilon_hat = _electron_energy_density(r, state);
        const ADReal n_e_hat = _electron_density(r, state);

        if (!std::isfinite(n_e_hat.value()))
          mooseError(
              "PhysicsElectronMeanEnergyMaterial requires finite n_e_hat; got ",
              n_e_hat.value(),
              ".");

        if (n_e_hat.value() <= 0.0)
          mooseError(
              "PhysicsElectronMeanEnergyMaterial requires n_e_hat > 0; got ",
              n_e_hat.value(),
              ". No denominator floor is applied.");

        if (!std::isfinite(n_epsilon_hat.value()))
          mooseError(
              "PhysicsElectronMeanEnergyMaterial requires finite n_epsilon_hat; got ",
              n_epsilon_hat.value(),
              ".");

        if (n_epsilon_hat.value() < 0.0)
          mooseError(
              "PhysicsElectronMeanEnergyMaterial requires n_epsilon_hat >= 0; got ",
              n_epsilon_hat.value(),
              ".");

        const ADReal mean_en_solved =
            _energy_reference_eV * n_epsilon_hat / n_e_hat;

        if (!std::isfinite(mean_en_solved.value()))
          mooseError(
              "PhysicsElectronMeanEnergyMaterial requires finite mean_en_solved; got ",
              mean_en_solved.value(),
              " eV. No clamp is applied.");

        return mean_en_solved;
      });
}
