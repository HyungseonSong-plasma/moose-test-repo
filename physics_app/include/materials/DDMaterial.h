#pragma once

#include "FunctorMaterial.h"
#include "PhysicsLookupTable1D.h"

#include <memory>
#include <string>

/**
 * Drift-diffusion transport coefficients for one species.
 *
 * model=constant: physical mu [m^2/(V s)] and D [m^2/s].
 * model=lookup: 1D table (coordinate, mobility, diffusivity), interpreted
 * as reduced mu*Nn and D*Nn or as physical values via table_units.
 *
 * For species=e, the same closure publishes the 5/3 electron energy
 * mobility/diffusion projection. It does not calculate Chemistry rates.
 */
class DDMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  DDMaterial(const InputParameters & parameters);

protected:
  enum class BoundsPolicy { Error, Clamp };

  ADReal interpolate(const ADReal & coordinate, std::size_t value_index) const;
  ADReal neutralNumberDensity(const auto & r, const auto & state) const;
  ADReal mobility(const auto & r, const auto & state) const;
  ADReal diffusivity(const auto & r, const auto & state) const;

  const std::string _species;
  const bool _lookup;
  const bool _reduced;
  const Real _constant_mobility;
  const Real _constant_diffusivity;
  const Moose::Functor<ADReal> * _coordinate = nullptr;
  const Moose::Functor<ADReal> * _pressure = nullptr;
  const Moose::Functor<ADReal> * _gas_temperature = nullptr;
  std::unique_ptr<PhysicsLookupTable1D> _table;
  BoundsPolicy _bounds_policy;
};
