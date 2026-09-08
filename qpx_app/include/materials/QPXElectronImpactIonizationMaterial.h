#pragma once

#include "FunctorMaterial.h"
#include "QPXLookupTable1D.h"

/**
 * Canonical electron-impact O2 ionization rate/source owner for R2.
 *
 * Reaction: e + O2 -> 2e + O2p
 *
 * The supplied table stores k_raw [m^3/(mol s)] versus solved mean electron
 * energy [eV]. One molar reaction progress is computed and shared by all
 * particle source paths:
 *
 *   R_ion_O2 = k_raw * (n_e / N_A) * c_O2  [mol/(m^3 s)]
 *
 * This object intentionally owns no electron-energy source; that coupling is
 * deferred to #26 E8 and must reuse the same reaction progress.
 */
class QPXElectronImpactIonizationMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  QPXElectronImpactIonizationMaterial(const InputParameters & parameters);

protected:
  ADReal interpolateStrict(const ADReal & mean_energy) const;

  const Moose::Functor<ADReal> & _mean_energy;
  const Moose::Functor<ADReal> & _electron_number_density;
  const Moose::Functor<ADReal> & _o2_molar_concentration;
  FileName _rate_table_file;
  QPXLookupTable1D _table;
  const Real _o2_molar_mass;
};
