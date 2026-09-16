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

  params.addParam<bool>(
      "use_trial_state_fallback",
      false,
      "If true, invalid intermediate nonlinear trial states with n_e_hat <= 0 or "
      "n_epsilon_hat < 0 return a fixed positive mean energy instead of aborting. "
      "This does not modify the solved variables.");
  params.addParam<Real>(
      "trial_fallback_mean_energy_eV",
      0.0,
      "Positive mean electron energy [eV] returned only for invalid nonlinear trial states "
      "when use_trial_state_fallback=true.");

  return params;
}

PhysicsElectronMeanEnergyMaterial::PhysicsElectronMeanEnergyMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _electron_energy_density(getFunctor<ADReal>("electron_energy_density")),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _energy_reference_eV(getParam<Real>("energy_reference_eV")),
    _use_trial_state_fallback(getParam<bool>("use_trial_state_fallback")),
    _trial_fallback_mean_energy_eV(getParam<Real>("trial_fallback_mean_energy_eV"))
{
  if (!std::isfinite(_energy_reference_eV) || _energy_reference_eV <= 0.0)
    paramError("energy_reference_eV", "Electron-energy normalization scale must be finite and positive.");
  if (_use_trial_state_fallback &&
      (!std::isfinite(_trial_fallback_mean_energy_eV) || _trial_fallback_mean_energy_eV <= 0.0))
    paramError("trial_fallback_mean_energy_eV",
               "A finite positive fallback mean energy is required when trial fallback is enabled.");

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

        if (!std::isfinite(n_epsilon_hat.value()))
          mooseError(
              "PhysicsElectronMeanEnergyMaterial requires finite n_epsilon_hat; got ",
              n_epsilon_hat.value(),
              ".");

        const bool invalid_trial = n_e_hat.value() <= 0.0 || n_epsilon_hat.value() < 0.0;
        if (invalid_trial)
        {
          if (_use_trial_state_fallback)
            return ADReal(_trial_fallback_mean_energy_eV);

          if (n_e_hat.value() <= 0.0)
            mooseError(
                "PhysicsElectronMeanEnergyMaterial requires n_e_hat > 0; got ",
                n_e_hat.value(),
                ". No denominator floor is applied.");

          mooseError(
              "PhysicsElectronMeanEnergyMaterial requires n_epsilon_hat >= 0; got ",
              n_epsilon_hat.value(),
              ".");
        }

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
