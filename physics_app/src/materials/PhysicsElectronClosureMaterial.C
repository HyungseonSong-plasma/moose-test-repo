#include "PhysicsElectronClosureMaterial.h"
#include "Physics.h"

#include <cmath>
#include <stdexcept>

registerMooseObject("PhysicsApp", PhysicsElectronClosureMaterial);

InputParameters
PhysicsElectronClosureMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Unified electron mean-energy and transport closure for the normalized FV electron state.");

  params.addRequiredParam<MooseFunctorName>(
      "normalized_electron_density",
      "Normalized electron number-density state n_e_hat.");
  params.addRequiredParam<MooseFunctorName>(
      "normalized_electron_energy_density",
      "Normalized electron energy-density state n_epsilon_hat.");
  params.addRequiredParam<Real>(
      "electron_energy_reference_eV",
      "Positive normalization scale epsilon_ref used in mean_energy = "
      "epsilon_ref*n_epsilon_hat/n_e_hat [eV].");
  params.addRequiredParam<MooseFunctorName>(
      "gas_pressure", "Absolute neutral-gas pressure [Pa].");
  params.addRequiredParam<MooseFunctorName>(
      "gas_temperature", "Neutral-gas temperature [K].");
  params.addRequiredParam<FileName>(
      "transport_table_file",
      "Three-column table: mean electron energy [eV], mu_e*N_n, D_e*N_n.");
  params.addParam<std::string>(
      "lookup_bounds_policy",
      "error",
      "Lookup behavior outside the electron transport table: 'error' or 'clamp'.");

  params.addParam<MooseFunctorName>(
      "electron_mean_energy_output",
      "electron_mean_energy_eV",
      "Published mean-electron-energy functor [eV].");
  params.addParam<MooseFunctorName>(
      "electron_temperature_output",
      "electron_temperature_K",
      "Published electron-temperature functor [K].");
  params.addParam<MooseFunctorName>(
      "neutral_number_density_output",
      "neutral_number_density",
      "Published neutral number-density functor [1/m^3].");
  params.addParam<MooseFunctorName>(
      "electron_reduced_mobility_output",
      "electron_reduced_mobility",
      "Published reduced electron mobility mu_e*N_n.");
  params.addParam<MooseFunctorName>(
      "electron_reduced_diffusion_output",
      "electron_reduced_diffusion",
      "Published reduced electron diffusion D_e*N_n.");
  params.addParam<MooseFunctorName>(
      "electron_mobility_output",
      "electron_mobility",
      "Published electron mobility [m^2/(V s)].");
  params.addParam<MooseFunctorName>(
      "electron_diffusion_output",
      "electron_diffusion",
      "Published electron diffusion coefficient [m^2/s].");
  params.addParam<MooseFunctorName>(
      "electron_energy_mobility_output",
      "electron_energy_mobility",
      "Published electron-energy mobility [m^2/(V s)].");
  params.addParam<MooseFunctorName>(
      "electron_energy_diffusion_output",
      "electron_energy_diffusion",
      "Published electron-energy diffusion coefficient [m^2/s].");

  return params;
}

PhysicsElectronClosureMaterial::PhysicsElectronClosureMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _normalized_electron_density(getFunctor<ADReal>("normalized_electron_density")),
    _normalized_electron_energy_density(
        getFunctor<ADReal>("normalized_electron_energy_density")),
    _gas_pressure(getFunctor<ADReal>("gas_pressure")),
    _gas_temperature(getFunctor<ADReal>("gas_temperature")),
    _electron_energy_reference_eV(getParam<Real>("electron_energy_reference_eV")),
    _transport_table_file(getParam<FileName>("transport_table_file")),
    _table(_transport_table_file, 1, {2, 3}),
    _bounds_policy(parseBoundsPolicy(getParam<std::string>("lookup_bounds_policy")))
{
  if (!std::isfinite(_electron_energy_reference_eV) ||
      _electron_energy_reference_eV <= 0.0)
    paramError("electron_energy_reference_eV",
               "Electron-energy normalization scale must be finite and positive.");

  const auto mean_energy = [this](const auto & r, const auto & state) -> ADReal
  {
    const ADReal n_hat = _normalized_electron_density(r, state);
    const ADReal eps_hat = _normalized_electron_energy_density(r, state);

    if (!std::isfinite(n_hat.value()) || n_hat.value() <= 0.0)
      mooseError("PhysicsElectronClosureMaterial requires normalized_electron_density > 0; got ",
                 n_hat.value(),
                 ".");

    if (!std::isfinite(eps_hat.value()) || eps_hat.value() < 0.0)
      mooseError(
          "PhysicsElectronClosureMaterial requires normalized_electron_energy_density >= 0; got ",
          eps_hat.value(),
          ".");

    const ADReal value = _electron_energy_reference_eV * eps_hat / n_hat;

    if (!std::isfinite(value.value()))
      mooseError("PhysicsElectronClosureMaterial produced non-finite mean electron energy.");

    return value;
  };

  const auto neutral_density = [this](const auto & r, const auto & state) -> ADReal
  {
    const ADReal pressure = _gas_pressure(r, state);
    const ADReal temperature = _gas_temperature(r, state);

    if (pressure.value() <= 0.0)
      mooseError("PhysicsElectronClosureMaterial requires gas_pressure > 0 Pa.");

    if (temperature.value() <= 0.0)
      mooseError("PhysicsElectronClosureMaterial requires gas_temperature > 0 K.");

    return pressure / (PHYSICS_CONSTANTS::k_boltz * temperature);
  };

  const auto mean_energy_name =
      getParam<MooseFunctorName>("electron_mean_energy_output");
  const auto electron_temperature_name =
      getParam<MooseFunctorName>("electron_temperature_output");
  const auto neutral_density_name =
      getParam<MooseFunctorName>("neutral_number_density_output");

  addFunctorProperty<ADReal>(mean_energy_name, mean_energy);

  addFunctorProperty<ADReal>(
      electron_temperature_name,
      [mean_energy](const auto & r, const auto & state) -> ADReal
      {
        constexpr Real two_thirds = 2.0 / 3.0;
        return two_thirds * mean_energy(r, state) * PHYSICS_CONSTANTS::e /
               PHYSICS_CONSTANTS::k_boltz;
      });

  addFunctorProperty<ADReal>(neutral_density_name, neutral_density);

  addFunctorProperty<ADReal>(
      getParam<MooseFunctorName>("electron_reduced_mobility_output"),
      [this, mean_energy](const auto & r, const auto & state) -> ADReal
      { return interpolate(mean_energy(r, state), 0); });

  addFunctorProperty<ADReal>(
      getParam<MooseFunctorName>("electron_reduced_diffusion_output"),
      [this, mean_energy](const auto & r, const auto & state) -> ADReal
      { return interpolate(mean_energy(r, state), 1); });

  addFunctorProperty<ADReal>(
      getParam<MooseFunctorName>("electron_mobility_output"),
      [this, mean_energy, neutral_density](const auto & r, const auto & state) -> ADReal
      { return interpolate(mean_energy(r, state), 0) / neutral_density(r, state); });

  addFunctorProperty<ADReal>(
      getParam<MooseFunctorName>("electron_diffusion_output"),
      [this, mean_energy, neutral_density](const auto & r, const auto & state) -> ADReal
      { return interpolate(mean_energy(r, state), 1) / neutral_density(r, state); });

  constexpr Real energy_transport_factor = 5.0 / 3.0;

  addFunctorProperty<ADReal>(
      getParam<MooseFunctorName>("electron_energy_mobility_output"),
      [this, mean_energy, neutral_density](const auto & r, const auto & state) -> ADReal
      {
        return energy_transport_factor * interpolate(mean_energy(r, state), 0) /
               neutral_density(r, state);
      });

  addFunctorProperty<ADReal>(
      getParam<MooseFunctorName>("electron_energy_diffusion_output"),
      [this, mean_energy, neutral_density](const auto & r, const auto & state) -> ADReal
      {
        return energy_transport_factor * interpolate(mean_energy(r, state), 1) /
               neutral_density(r, state);
      });
}

PhysicsElectronClosureMaterial::BoundsPolicy
PhysicsElectronClosureMaterial::parseBoundsPolicy(const std::string & value)
{
  if (value == "error")
    return BoundsPolicy::Error;

  if (value == "clamp")
    return BoundsPolicy::Clamp;

  throw std::runtime_error(
      "PhysicsElectronClosureMaterial lookup_bounds_policy must be 'error' or 'clamp'.");
}

ADReal
PhysicsElectronClosureMaterial::interpolate(const ADReal & coordinate,
                                             std::size_t value_index) const
{
  const auto & x = _table.coordinate();
  const auto & y = _table.values(value_index);
  const Real raw = coordinate.value();

  if (raw < x.front())
  {
    if (_bounds_policy == BoundsPolicy::Error)
      mooseError("Mean electron energy ",
                 raw,
                 " eV is below electron transport table minimum ",
                 x.front(),
                 " eV.");

    return y.front();
  }

  if (raw > x.back())
  {
    if (_bounds_policy == BoundsPolicy::Error)
      mooseError("Mean electron energy ",
                 raw,
                 " eV is above electron transport table maximum ",
                 x.back(),
                 " eV.");

    return y.back();
  }

  if (raw == x.front())
    return y.front();

  if (raw == x.back())
    return y.back();

  const std::size_t i = _table.lowerBracket(raw);
  return y[i] +
         (coordinate - x[i]) * (y[i + 1] - y[i]) / (x[i + 1] - x[i]);
}
