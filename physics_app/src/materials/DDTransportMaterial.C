#include "DDTransportMaterial.h"
#include "Physics.h"

#include <cctype>
#include <cmath>
#include <stdexcept>

registerMooseObject("PhysicsApp", DDTransportMaterial);

InputParameters
DDTransportMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription("Species-owned drift-diffusion mobility and diffusivity "
                             "from physical constants, existing AD Functors or a one-dimensional lookup.");
  params.addParam<std::string>("species_id", "e", "Solver-safe species identifier.");
  params.addParam<MooseEnum>("model", MooseEnum("lookup constant functor", "lookup"),
                             "Transport source: lookup table, physical constants or existing AD Functors.");
  params.addParam<MooseFunctorName>(
      "mobility_source",
      "Optional upstream Native coefficient source; otherwise model=functor reads "
      "<species>_mobility from another Material.");
  params.addParam<MooseFunctorName>(
      "diffusivity_source",
      "Optional upstream Native coefficient source; otherwise model=functor reads "
      "<species>_diffusivity from another Material.");
  params.addParam<Real>("mobility", "Constant species mobility [m^2/(V s)].");
  params.addParam<Real>("diffusivity", "Constant species diffusivity [m^2/s].");
  params.addParam<FileName>(
      "table_file",
      "Three-column lookup table: e_energy_eV [eV], mobility, diffusivity. "
      "Lookup energy is fixed to the solved electron mean energy.");
  params.addParam<bool>(
      "fluid_energy",
      true,
      "Enable 5/3 electron energy transport from the same particle mobility "
      "and diffusivity. Physics/JSON sets this from species.e.energy_transport_coef=fluid.");
  params.addParam<MooseEnum>("table_units", MooseEnum("reduced physical", "reduced"),
                             "Reduced values mu*N_n/D*N_n or physical mu/D.");
  params.addParam<MooseFunctorName>("pressure", "Neutral-gas pressure [Pa] for reduced tables.");
  params.addParam<MooseFunctorName>("gas_temperature",
                                    "Neutral-gas temperature [K] for reduced tables.");
  params.addParam<std::string>("bounds_policy", "error",
                               "Outside table: fail closed or clamp ('error'/'clamp').");
  return params;
}

DDTransportMaterial::DDTransportMaterial(const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _species(getParam<std::string>("species_id")),
    _lookup(getParam<MooseEnum>("model") == "lookup"),
    _functor(getParam<MooseEnum>("model") == "functor"),
    _reduced(getParam<MooseEnum>("table_units") == "reduced"),
    _constant_mobility(isParamValid("mobility") ? getParam<Real>("mobility") : 0.0),
    _constant_diffusivity(isParamValid("diffusivity") ? getParam<Real>("diffusivity") : 0.0),
    _bounds_policy(getParam<std::string>("bounds_policy") == "clamp" ?
                   BoundsPolicy::Clamp : BoundsPolicy::Error)
{
  if (_species.empty() || !std::isalpha(static_cast<unsigned char>(_species.front())))
    paramError("species_id", "Species ID must start with a letter.");
  for (const char c : _species)
    if (!std::isalnum(static_cast<unsigned char>(c)) && c != '_')
      paramError("species_id", "Species ID must be alphanumeric or underscore.");

  const auto & bounds = getParam<std::string>("bounds_policy");
  if (bounds != "error" && bounds != "clamp")
    paramError("bounds_policy", "Expected 'error' or 'clamp'.");

  if (_functor)
  {
    // Canonical inputs are already supplied by the upstream Native/Plasma
    // Material; do not accidentally create an alias to our own output.
    // Explicit source names bridge the currently used Native ion coefficient providers.
    const bool explicit_mu = isParamValid("mobility_source");
    const bool explicit_D = isParamValid("diffusivity_source");
    const MooseFunctorName mu = explicit_mu
                                   ? getParam<MooseFunctorName>("mobility_source")
                                   : MooseFunctorName(_species + "_mobility");
    const MooseFunctorName diffusion = explicit_D
                                          ? getParam<MooseFunctorName>("diffusivity_source")
                                          : MooseFunctorName(_species + "_diffusivity");
    // Canonical external names must not be republished, preventing cycles.
    // Existing electron_* outputs are live transport-kernel interfaces and
    // cannot be used as their own source inputs.
    if (_species == "e" && (mu == "electron_mobility" ||
                            diffusion == "electron_diffusion"))
      paramError("model", "Functor mode may not consume its own electron aliases.");
    for (const char * name : {"mobility", "diffusivity", "table_file",
                              "pressure", "gas_temperature"})
      if (isParamValid(name))
        paramError("model", "Functor mode forbids unrelated coefficient input: ", name);
    if (isParamSetByUser("table_units") || isParamSetByUser("bounds_policy"))
      paramError("model", "Functor mode must not set lookup units or bounds policy.");
    _mobility_source = explicit_mu ? &getFunctor<ADReal>("mobility_source")
                                   : &getFunctorByName<ADReal>(mu);
    _diffusivity_source = explicit_D ? &getFunctor<ADReal>("diffusivity_source")
                                     : &getFunctorByName<ADReal>(diffusion);
  }
  else if (_lookup)
  {
    if (isParamValid("mobility_source") || isParamValid("diffusivity_source"))
      paramError("model", "Lookup mode forbids mobility_source or diffusivity_source.");
    if (!isParamValid("table_file"))
      paramError("table_file", "Lookup transport requires table_file.");
    // All lookup coefficients are indexed by solved mean electron energy.
    // No user-provided coordinate or alternate state name is accepted.
    _mean_energy = &getFunctorByName<ADReal>("e_energy_eV");
    const auto & filename = getParam<FileName>("table_file");
    _table = std::make_unique<PhysicsLookupTable1D>(filename, 1, std::vector<std::size_t>{2, 3});
    // Do not silently propagate NaN, infinity or negative transport data
    // through mobility/diffusivity Functors, especially with table_units=reduced.
    for (const Real coordinate : _table->coordinate())
      if (!std::isfinite(coordinate))
        paramError("table_file", "DDTransportMaterial lookup coordinate must be finite.");
    for (std::size_t column = 0; column < 2; ++column)
      for (const Real coefficient : _table->values(column))
        if (!std::isfinite(coefficient) || coefficient < 0.0)
          paramError("table_file",
                     "DDTransportMaterial lookup coefficients must be finite and nonnegative.");
    if (_reduced)
    {
      if (!isParamValid("pressure") || !isParamValid("gas_temperature"))
        paramError("table_units", "Reduced transport requires pressure and gas_temperature.");
      _pressure = &getFunctor<ADReal>("pressure");
      _gas_temperature = &getFunctor<ADReal>("gas_temperature");
    }
  }
  else
  {
    if (!isParamValid("mobility") || !isParamValid("diffusivity"))
      paramError("model", "Constant transport requires mobility and diffusivity.");
    if (!std::isfinite(_constant_mobility) || !std::isfinite(_constant_diffusivity) ||
        _constant_mobility < 0.0 || _constant_diffusivity < 0.0)
      paramError("model", "Mobility and diffusivity must be finite and nonnegative.");
    for (const char * name : {"table_file", "mobility_source", "diffusivity_source"})
      if (isParamValid(name))
        paramError("model", "Constant mode must not also specify lookup inputs: ", name);
  }

  const auto particle_mu = [this](const auto & r, const auto & state) -> ADReal
  { return mobility(r, state); };
  const auto particle_D = [this](const auto & r, const auto & state) -> ADReal
  { return diffusivity(r, state); };

  // When the source already has the canonical species name, its original
  // Native producer retains ownership; re-registering it would duplicate
  // a Functor name or form a self-reference cycle.
  const bool external_mobility =
      _functor && (!isParamValid("mobility_source") ||
                   getParam<MooseFunctorName>("mobility_source") == _species + "_mobility");
  const bool external_diffusivity =
      _functor && (!isParamValid("diffusivity_source") ||
                   getParam<MooseFunctorName>("diffusivity_source") == _species + "_diffusivity");
  if (!external_mobility)
    addFunctorProperty<ADReal>(_species + "_mobility", particle_mu);
  if (!external_diffusivity)
    addFunctorProperty<ADReal>(_species + "_diffusivity", particle_D);

  if (_species == "e")
  {
    // Historical electron_* consumers and modern species-ID consumers share one
    // numerical closure, never an independently interpolated/coefficient source.
    addFunctorProperty<ADReal>("electron_mobility", particle_mu);
    addFunctorProperty<ADReal>("electron_diffusion", particle_D);
    if (getParam<bool>("fluid_energy"))
    {
    constexpr Real energy_factor = 5.0 / 3.0;
    addFunctorProperty<ADReal>(
        "e_energy_mobility",
        [this, energy_factor](const auto & r, const auto & state) -> ADReal
        { return energy_factor * mobility(r, state); });
    addFunctorProperty<ADReal>(
        "e_energy_diffusivity",
        [this, energy_factor](const auto & r, const auto & state) -> ADReal
        { return energy_factor * diffusivity(r, state); });
    addFunctorProperty<ADReal>(
        "electron_energy_mobility",
        [this, energy_factor](const auto & r, const auto & state) -> ADReal
        { return energy_factor * mobility(r, state); });
    addFunctorProperty<ADReal>(
        "electron_energy_diffusion",
        [this, energy_factor](const auto & r, const auto & state) -> ADReal
        { return energy_factor * diffusivity(r, state); });
    }

    if (_lookup && _reduced)
    {
      addFunctorProperty<ADReal>(
          "neutral_number_density",
          [this](const auto & r, const auto & state) -> ADReal
          { return neutralNumberDensity(r, state); });
      addFunctorProperty<ADReal>(
          "electron_reduced_mobility",
          [this](const auto & r, const auto & state) -> ADReal
          { return interpolate((*_mean_energy)(r, state), 0); });
      addFunctorProperty<ADReal>(
          "electron_reduced_diffusion",
          [this](const auto & r, const auto & state) -> ADReal
          { return interpolate((*_mean_energy)(r, state), 1); });
    }
  }
}

ADReal
DDTransportMaterial::interpolate(const ADReal & coordinate, std::size_t value_index) const
{
  const auto & x = _table->coordinate();
  const auto & y = _table->values(value_index);
  const Real raw = coordinate.value();

  if (!std::isfinite(raw))
    mooseError("DDTransportMaterial lookup coordinate must be finite.");
  if (raw < x.front())
  {
    if (_bounds_policy == BoundsPolicy::Error)
      mooseError("DDTransportMaterial lookup coordinate ", raw, " is below ", x.front(), ".");
    return y.front();
  }
  if (raw > x.back())
  {
    if (_bounds_policy == BoundsPolicy::Error)
      mooseError("DDTransportMaterial lookup coordinate ", raw, " is above ", x.back(), ".");
    return y.back();
  }
  if (raw == x.front()) return y.front();
  if (raw == x.back()) return y.back();

  const std::size_t i = _table->lowerBracket(raw);
  return y[i] + (coordinate - x[i]) * (y[i+1] - y[i]) / (x[i+1] - x[i]);
}
