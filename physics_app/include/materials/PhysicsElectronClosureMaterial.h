#pragma once

#include "FunctorMaterial.h"
#include "PhysicsLookupTable1D.h"

#include <cstddef>
#include <string>

/**
 * Unified local-mean-energy electron closure.
 *
 * Inputs:
 *   - normalized electron number-density state
 *   - normalized electron energy-density state
 *   - neutral-gas pressure and temperature
 *   - reduced electron transport table
 *
 * Outputs are configurable functor names and include:
 *   - mean electron energy [eV]
 *   - electron temperature [K]
 *   - neutral number density [1/m^3]
 *   - reduced/physical electron mobility and diffusion
 *   - Maxwellian 5/3 electron-energy mobility and diffusion
 */
class PhysicsElectronClosureMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronClosureMaterial(const InputParameters & parameters);

protected:
  enum class BoundsPolicy
  {
    Error,
    Clamp
  };

  ADReal interpolate(const ADReal & coordinate, std::size_t value_index) const;
  static BoundsPolicy parseBoundsPolicy(const std::string & value);

  const Moose::Functor<ADReal> & _normalized_electron_density;
  const Moose::Functor<ADReal> & _normalized_electron_energy_density;
  const Moose::Functor<ADReal> & _gas_pressure;
  const Moose::Functor<ADReal> & _gas_temperature;

  const Real _electron_energy_reference_eV;
  const FileName _transport_table_file;
  PhysicsLookupTable1D _table;
  const BoundsPolicy _bounds_policy;
};
