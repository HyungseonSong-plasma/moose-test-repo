#include "DDMaterial.h"
#include "Physics.h"

#include <cctype>
#include <cmath>
#include <stdexcept>

registerMooseObject("PhysicsApp", DDMaterial);
// Factory-input compatibility only; the old C++ lookup class is removed.
registerMooseObjectAliased("PhysicsApp", DDMaterial, "ElectronTransportLookupMaterial");
registerMooseObjectAliased("PhysicsApp", DDMaterial, "PhysicsElectronTransportLookupMaterial");

InputParameters
DDMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription("Species-owned drift-diffusion mobility and diffusivity "
                             "from physical constants, existing AD Functors or a one-dimensional lookup.");
  params.addParam<std::string>("species_id", "e", "Solver-safe species identifier.");
  params.addParam<MooseEnum>("model", MooseEnum("lookup constant functor", "lookup"),
                             "Transport source: lookup table, physical constants or existing AD Functors.");
  params.addParam<MooseFunctorName>("mobility_source",
                                    "Existing mobility [m^2/(V s)] for model=functor.");
  params.addParam<MooseFunctorName>("diffusivity_source",
                                    "Existing diffusivity [m^2/s] for model=functor.");
  params.addParam<Real>("mobility", "Constant species mobility [m^2/(V s)].");
  params.addParam<Real>("diffusivity", "Constant species diffusivity [m^2/s].");
  params.addParam<FileName>("table_file", "Three-column lookup table: x, mobility, diffusivity.");
  params.addParam<FileName>("property_table_file",
                            "Deprecated lookup filename accepted for historical MOOSE inputs.");
  params.addParam<MooseFunctorName>("coordinate", "Lookup coordinate Functor.");
  params.addParam<MooseFunctorName>("mean_energy",
                                    "Historical lookup coordinate; mean electron energy [eV].");
  params.addParam<MooseEnum>("table_units", MooseEnum("reduced physical", "reduced"),
                             "Reduced values mu*N_n/D*N_n or physical mu/D.");
  params.addParam<MooseFunctorName>("pressure", "Neutral-gas pressure [Pa] for reduced tables.");
  params.addParam<MooseFunctorName>("gas_temperature",
                                    "Neutral-gas temperature [K] for reduced tables.");
  params.addParam<std::string>("bounds_policy", "error",
                               "Outside table: fail closed or clamp ('error'/'clamp').");
  return params;
}

DDMaterial::DDMaterial(const InputParameters & parameters)
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
    if (!isParamValid("mobility_source") || !isParamValid("diffusivity_source"))
      paramError("model", "Functor mode requires mobility_source and diffusivity_source.");
    const auto mu = getParam<MooseFunctorName>("mobility_source");
    const auto diffusion = getParam<MooseFunctorName>("diffusivity_source");
    if (mu == _species + "_mobility" || diffusion == _species + "_diffusivity" ||
        (_species == "e" && (mu == "electron_mobility" ||
                             diffusion == "electron_diffusion")))
      paramError("model", "Functor mode may not consume its own published coefficients.");
    for (const char * name : {"mobility", "diffusivity", "table_file", "property_table_file",
                              "coordinate", "mean_energy", "pressure", "gas_temperature"})
      if (isParamValid(name))
        paramError("model", "Functor mode forbids unrelated coefficient input: ", name);
    if (isParamSetByUser("table_units") || isParamSetByUser("bounds_policy"))
      paramError("model", "Functor mode must not set lookup units or bounds policy.");
    _mobility_source = &getFunctor<ADReal>("mobility_source");
    _diffusivity_source = &getFunctor<ADReal>("diffusivity_source");
  }
  else if (_lookup)
  {
    if (isParamValid("mobility_source") || isParamValid("diffusivity_source"))
      paramError("model", "Lookup mode forbids mobility_source or diffusivity_source.");
    const bool new_file = isParamValid("table_file");
    const bool old_file = isParamValid("property_table_file");
    if (new_file == old_file)
      paramError("table_file", "Specify exactly one table_file or property_table_file.");
    const bool coordinate = isParamValid("coordinate");
    const bool mean_energy = isParamValid("mean_energy");
    if (coordinate == mean_energy)
      paramError("coordinate", "Specify exactly one coordinate or mean_energy Functor.");
    _coordinate = &getFunctor<ADReal>(coordinate ? "coordinate" : "mean_energy");
    const auto & filename = new_file ? getParam<FileName>("table_file") :
                                       getParam<FileName>("property_table_file");
    _table = std::make_unique<PhysicsLookupTable1D>(filename, 1, std::vector<std::size_t>{2, 3});
    // Do not silently propagate NaN, infinity or negative transport data
    // through mobility/diffusivity Functors, especially with table_units=reduced.
    for (const Real coordinate : _table->coordinate())
      if (!std::isfinite(coordinate))
        paramError("table_file", "DDMaterial lookup coordinate must be finite.");
    for (std::size_t column = 0; column < 2; ++column)
      for (const Real coefficient : _table->values(column))
        if (!std::isfinite(coefficient) || coefficient < 0.0)
          paramError("table_file",
                     "DDMaterial lookup coefficients must be finite and nonnegative.");
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
    for (const char * name : {"table_file", "property_table_file", "coordinate",
                              "mean_energy", "mobility_source", "diffusivity_source"})
      if (isParamValid(name))
        paramError("model", "Constant mode must not also specify lookup inputs: ", name);
  }

  const auto particle_mu = [this](const auto & r, const auto & state) -> ADReal
  { return mobility(r, state); };
  const auto particle_D = [this](const auto & r, const auto & state) -> ADReal
  { return diffusivity(r, state); };

  addFunctorProperty<ADReal>(_species + "_mobility", particle_mu);
  addFunctorProperty<ADReal>(_species + "_diffusivity", particle_D);

  if (_species == "e")
  {
    // Historical electron_* consumers and modern species-ID consumers share one
    // numerical closure, never an independently interpolated/coefficient source.
    addFunctorProperty<ADReal>("electron_mobility", particle_mu);
    addFunctorProperty<ADReal>("electron_diffusion", particle_D);
    constexpr Real energy_factor = 5.0 / 3.0;
    addFunctorProperty<ADReal>(
        "electron_energy_mobility",
        [this, energy_factor](const auto & r, const auto & state) -> ADReal
        { return energy_factor * mobility(r, state); });
    addFunctorProperty<ADReal>(
        "electron_energy_diffusion",
        [this, energy_factor](const auto & r, const auto & state) -> ADReal
        { return energy_factor * diffusivity(r, state); });

    if (_lookup && _reduced)
    {
      addFunctorProperty<ADReal>(
          "neutral_number_density",
          [this](const auto & r, const auto & state) -> ADReal
          { return neutralNumberDensity(r, state); });
      addFunctorProperty<ADReal>(
          "electron_reduced_mobility",
          [this](const auto & r, const auto & state) -> ADReal
          { return interpolate((*_coordinate)(r, state), 0); });
      addFunctorProperty<ADReal>(
          "electron_reduced_diffusion",
          [this](const auto & r, const auto & state) -> ADReal
          { return interpolate((*_coordinate)(r, state), 1); });
    }
  }
}

ADReal
DDMaterial::interpolate(const ADReal & coordinate, std::size_t value_index) const
{
  const auto & x = _table->coordinate();
  const auto & y = _table->values(value_index);
  const Real raw = coordinate.value();

  if (!std::isfinite(raw))
    mooseError("DDMaterial lookup coordinate must be finite.");
  if (raw < x.front())
  {
    if (_bounds_policy == BoundsPolicy::Error)
      mooseError("DDMaterial lookup coordinate ", raw, " is below ", x.front(), ".");
    return y.front();
  }
  if (raw > x.back())
  {
    if (_bounds_policy == BoundsPolicy::Error)
      mooseError("DDMaterial lookup coordinate ", raw, " is above ", x.back(), ".");
    return y.back();
  }
  if (raw == x.front()) return y.front();
  if (raw == x.back()) return y.back();

  const std::size_t i = _table->lowerBracket(raw);
  return y[i] + (coordinate - x[i]) * (y[i+1] - y[i]) / (x[i+1] - x[i]);
}
