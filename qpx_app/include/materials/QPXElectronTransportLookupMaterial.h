#pragma once

#include "FunctorMaterial.h"
#include "QPXLookupTable1D.h"

/**
 * Electron transport closure based on the supplied reduced-coefficient table.
 *
 * Table columns:
 *   1 : mean electron energy [eV]
 *   2 : mu_e * N_n
 *   3 : D_e * N_n
 *
 * Runtime conversion:
 *
 *   N_n  = p / (k_B T_g)
 *   mu_e = (mu_e N_n) / N_n
 *   D_e  = (D_e N_n) / N_n
 *
 * N_n is neutral-gas number density, not the Avogadro constant.
 */
class QPXElectronTransportLookupMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  QPXElectronTransportLookupMaterial(const InputParameters & parameters);

protected:
  enum class BoundsPolicy
  {
    Error,
    Clamp
  };

  ADReal interpolate(const ADReal & coordinate, std::size_t value_index) const;
  static BoundsPolicy parseBoundsPolicy(const std::string & value);

  const Moose::Functor<ADReal> & _mean_energy;
  const Moose::Functor<ADReal> & _pressure;
  const Moose::Functor<ADReal> & _gas_temperature;

  FileName _property_table_file;
  QPXLookupTable1D _table;
  BoundsPolicy _bounds_policy;
};
