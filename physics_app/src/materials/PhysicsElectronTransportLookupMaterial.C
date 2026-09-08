#include "PhysicsElectronTransportLookupMaterial.h"
#include "Physics.h"

#include <algorithm>
#include <stdexcept>

registerMooseObject("PhysicsApp", PhysicsElectronTransportLookupMaterial);

InputParameters
PhysicsElectronTransportLookupMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Interpolates reduced electron mobility and diffusion coefficient from a "
      "mean-energy table, converts them using the local neutral number density, "
      "and exposes the Maxwellian 5/3 electron-energy transport projection.");

  params.addRequiredParam<FileName>(
      "property_table_file",
      "Three-column table: mean energy, reduced mobility, reduced diffusion.");

  params.addRequiredParam<MooseFunctorName>(
      "mean_energy",
      "Mean electron energy lookup coordinate [eV].");

  params.addRequiredParam<MooseFunctorName>(
      "pressure",
      "Absolute neutral-gas pressure [Pa].");

  params.addRequiredParam<MooseFunctorName>(
      "gas_temperature",
      "Neutral-gas temperature [K].");

  params.addParam<std::string>(
      "bounds_policy",
      "error",
      "Lookup behavior outside the tabulated mean-energy range: 'error' or 'clamp'.");

  return params;
}

PhysicsElectronTransportLookupMaterial::PhysicsElectronTransportLookupMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _mean_energy(getFunctor<ADReal>("mean_energy")),
    _pressure(getFunctor<ADReal>("pressure")),
    _gas_temperature(getFunctor<ADReal>("gas_temperature")),
    _property_table_file(getParam<FileName>("property_table_file")),
    _table(_property_table_file, 1, {2, 3}),
    _bounds_policy(parseBoundsPolicy(getParam<std::string>("bounds_policy")))
{
  constexpr Real energy_transport_factor = 5.0 / 3.0;

  addFunctorProperty<ADReal>(
      "neutral_number_density",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal T_g = _gas_temperature(r, state);
        if (T_g.value() <= 0.0)
          mooseError("PhysicsElectronTransportLookupMaterial requires T_g > 0 K.");

        return _pressure(r, state) / (PHYSICS_CONSTANTS::k_boltz * T_g);
      });

  addFunctorProperty<ADReal>(
      "electron_reduced_mobility",
      [this](const auto & r, const auto & state) -> ADReal
      { return interpolate(_mean_energy(r, state), 0); });

  addFunctorProperty<ADReal>(
      "electron_reduced_diffusion",
      [this](const auto & r, const auto & state) -> ADReal
      { return interpolate(_mean_energy(r, state), 1); });

  addFunctorProperty<ADReal>(
      "electron_mobility",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal T_g = _gas_temperature(r, state);
        const ADReal N_n =
            _pressure(r, state) / (PHYSICS_CONSTANTS::k_boltz * T_g);

        return interpolate(_mean_energy(r, state), 0) / N_n;
      });

  addFunctorProperty<ADReal>(
      "electron_diffusion",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal T_g = _gas_temperature(r, state);
        const ADReal N_n =
            _pressure(r, state) / (PHYSICS_CONSTANTS::k_boltz * T_g);

        return interpolate(_mean_energy(r, state), 1) / N_n;
      });

  // Local-mean-energy closure used by the accepted Physics/Hagelaar path and COMSOL's
  // Maxwellian transport approximation. Keep particle and energy coefficients under
  // one lookup owner so a solved mean-energy coordinate cannot silently select a
  // different transport table or neutral-density conversion.
  addFunctorProperty<ADReal>(
      "electron_energy_mobility",
      [this, energy_transport_factor](const auto & r, const auto & state) -> ADReal
      {
        const ADReal T_g = _gas_temperature(r, state);
        const ADReal N_n =
            _pressure(r, state) / (PHYSICS_CONSTANTS::k_boltz * T_g);

        return energy_transport_factor * interpolate(_mean_energy(r, state), 0) / N_n;
      });

  addFunctorProperty<ADReal>(
      "electron_energy_diffusion",
      [this, energy_transport_factor](const auto & r, const auto & state) -> ADReal
      {
        const ADReal T_g = _gas_temperature(r, state);
        const ADReal N_n =
            _pressure(r, state) / (PHYSICS_CONSTANTS::k_boltz * T_g);

        return energy_transport_factor * interpolate(_mean_energy(r, state), 1) / N_n;
      });
}

PhysicsElectronTransportLookupMaterial::BoundsPolicy
PhysicsElectronTransportLookupMaterial::parseBoundsPolicy(const std::string & value)
{
  if (value == "error")
    return BoundsPolicy::Error;

  if (value == "clamp")
    return BoundsPolicy::Clamp;

  throw std::runtime_error(
      "PhysicsElectronTransportLookupMaterial bounds_policy must be 'error' or 'clamp'.");
}

ADReal
PhysicsElectronTransportLookupMaterial::interpolate(const ADReal & coordinate,
                                                std::size_t value_index) const
{
  const auto & x = _table.coordinate();
  const auto & y = _table.values(value_index);
  const Real x_raw = coordinate.value();

  if (x_raw < x.front())
  {
    if (_bounds_policy == BoundsPolicy::Error)
      mooseError("Mean electron energy ",
                 x_raw,
                 " eV is below the lookup-table minimum ",
                 x.front(),
                 " eV.");

    return y.front();
  }

  if (x_raw > x.back())
  {
    if (_bounds_policy == BoundsPolicy::Error)
      mooseError("Mean electron energy ",
                 x_raw,
                 " eV is above the lookup-table maximum ",
                 x.back(),
                 " eV.");

    return y.back();
  }

  if (x_raw == x.front())
    return y.front();

  if (x_raw == x.back())
    return y.back();

  const std::size_t i = _table.lowerBracket(x_raw);

  return y[i] +
         (coordinate - x[i]) * (y[i + 1] - y[i]) / (x[i + 1] - x[i]);
}
