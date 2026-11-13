#pragma once

#include "FunctorMaterial.h"
#include "PhysicsLookupTable1D.h"
#include "Physics.h"

#include <cmath>
#include <memory>
#include <string>

/**
 * Drift-diffusion transport coefficients for one species.
 *
 * model=constant: physical mu [m^2/(V s)] and D [m^2/s].
 * model=functor: source-preserving AD Functor forwarding.
 * model=lookup: 1D table (mean_en_solved [eV], mobility, diffusivity),
 * interpreted as reduced mu*Nn and D*Nn or as physical values via table_units.
 * The lookup axis is always mean_en_solved; it is not configurable.
 *
 * For species=e, the same closure publishes the 5/3 electron energy
 * mobility/diffusion projection. It does not calculate Chemistry rates.
 */
class DDTransportMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  DDTransportMaterial(const InputParameters & parameters);

protected:
  enum class BoundsPolicy { Error, Clamp };

  ADReal interpolate(const ADReal & coordinate, std::size_t value_index) const;
  template <typename Arg, typename State>
  ADReal neutralNumberDensity(const Arg & r, const State & state) const
  {
    const ADReal T_g = (*_gas_temperature)(r, state);
    const ADReal pressure = (*_pressure)(r, state);
    if (!std::isfinite(T_g.value()) || T_g.value() <= 0.0 ||
        !std::isfinite(pressure.value()) || pressure.value() <= 0.0)
      mooseError("DDTransportMaterial reduced table requires gas_temperature > 0 K and pressure > 0 Pa.");
    return pressure / (PHYSICS_CONSTANTS::k_boltz * T_g);
  }

  template <typename Arg, typename State>
  ADReal mobility(const Arg & r, const State & state) const
  {
    if (_functor)
      return (*_mobility_source)(r, state);
    if (!_lookup)
      return _constant_mobility;
    const ADReal raw = interpolate((*_mean_energy)(r, state), 0);
    return _reduced ? raw / neutralNumberDensity(r, state) : raw;
  }

  template <typename Arg, typename State>
  ADReal diffusivity(const Arg & r, const State & state) const
  {
    if (_functor)
      return (*_diffusivity_source)(r, state);
    if (!_lookup)
      return _constant_diffusivity;
    const ADReal raw = interpolate((*_mean_energy)(r, state), 1);
    return _reduced ? raw / neutralNumberDensity(r, state) : raw;
  }

  const std::string _species;
  const bool _lookup;
  const bool _functor;
  const bool _reduced;
  const Real _constant_mobility;
  const Real _constant_diffusivity;
  const Moose::Functor<ADReal> * _mobility_source = nullptr;
  const Moose::Functor<ADReal> * _diffusivity_source = nullptr;
  const Moose::Functor<ADReal> * _mean_energy = nullptr;
  const Moose::Functor<ADReal> * _pressure = nullptr;
  const Moose::Functor<ADReal> * _gas_temperature = nullptr;
  std::unique_ptr<PhysicsLookupTable1D> _table;
  BoundsPolicy _bounds_policy;
};
