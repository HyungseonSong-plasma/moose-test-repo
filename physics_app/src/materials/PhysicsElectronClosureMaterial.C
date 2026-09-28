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
      "Unified electron mean-energy and transport closure. Preferred physical mode "
      "uses number density [1/m^3] and electron energy density [eV/m^3].");

  params.addParam<MooseEnum>(
      "state_form",
      MooseEnum("normalized physical_eV", "normalized"),
      "Electron state convention.");
  params.addParam<MooseFunctorName>(
      "electron_number_density",
      "Physical electron number density [1/m^3] for state_form=physical_eV.");
  params.addParam<MooseFunctorName>(
      "electron_energy_density",
      "Physical electron energy density [eV/m^3] for state_form=physical_eV.");
  params.addParam<MooseFunctorName>(
      "normalized_electron_density",
      "Historical normalized electron number-density state.");
  params.addParam<MooseFunctorName>(
      "normalized_electron_energy_density",
      "Historical normalized electron energy-density state.");
  params.addParam<Real>(
      "electron_energy_reference_eV",
      "Historical normalization energy epsilon_ref [eV], used only in normalized mode.");
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
    _physical_state(getParam<MooseEnum>("state_form") == "physical_eV"),
    _electron_density(nullptr),
    _electron_energy_density(nullptr),
    _gas_pressure(getFunctor<ADReal>("gas_pressure")),
    _gas_temperature(getFunctor<ADReal>("gas_temperature")),
    _electron_energy_reference_eV(getParam<Real>("electron_energy_reference_eV")),
    _transport_table_file(getParam<FileName>("transport_table_file")),
    _table(_transport_table_file, 1, {2, 3}),
    _bounds_policy(parseBoundsPolicy(getParam<std::string>("lookup_bounds_policy")))
{
  if (_physical_state)
  {
    if (!isParamValid("electron_number_density"))
      paramError("electron_number_density",
                 "electron_number_density is required for state_form=physical_eV.");
    if (!isParamValid("electron_energy_density"))
      paramError("electron_energy_density",
                 "electron_energy_density is required for state_form=physical_eV.");
    _electron_density = &getFunctor<ADReal>("electron_number_density");
    _electron_energy_density = &getFunctor<ADReal>("electron_energy_density");
  }
  else
  {
    if (!isParamValid("normalized_electron_density"))
      paramError("normalized_electron_density",
                 "normalized_electron_density is required for state_form=normalized.");
    if (!isParamValid("normalized_electron_energy_density"))
      paramError("normalized_electron_energy_density",
                 "normalized_electron_energy_density is required for state_form=normalized.");
    if (!isParamValid("electron_energy_reference_eV"))
      paramError("electron_energy_reference_eV",
                 "electron_energy_reference_eV is required for state_form=normalized.");
    if (!std::isfinite(_electron_energy_reference_eV) ||
        _electron_energy_reference_eV <= 0.0)
      paramError("electron_energy_reference_eV",
                 "Electron-energy normalization scale must be finite and positive.");
    _electron_density = &getFunctor<ADReal>("normalized_electron_density");
    _electron_energy_density = &getFunctor<ADReal>("normalized_electron_energy_density");
  }

  const auto mean_energy = [this](const auto & r, const auto & state) -> ADReal
  {
    const ADReal density = (*_electron_density)(r, state);
    const ADReal energy_density = (*_electron_energy_density)(r, state);

    if (!std::isfinite(density.value()) || density.value() <= 0.0)
      mooseError("PhysicsElectronClosureMaterial requires electron density > 0; got ",
                 density.value(),
                 ".");

    if (!std::isfinite(energy_density.value()) || energy_density.value() < 0.0)
      mooseError(
          "PhysicsElectronClosureMaterial requires electron energy density >= 0; got ",
          energy_density.value(),
          ".");

    const ADReal value =
        _physical_state
            ? energy_density / density
            : _electron_energy_reference_eV * energy_density / density;

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
      [this, mean_energy, neutral_density, energy_transport_factor](const auto & r, const auto & state) -> ADReal
      {
        return energy_transport_factor * interpolate(mean_energy(r, state), 0) /
               neutral_density(r, state);
      });

  addFunctorProperty<ADReal>(
      getParam<MooseFunctorName>("electron_energy_diffusion_output"),
      [this, mean_energy, neutral_density, energy_transport_factor](const auto & r, const auto & state) -> ADReal
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
