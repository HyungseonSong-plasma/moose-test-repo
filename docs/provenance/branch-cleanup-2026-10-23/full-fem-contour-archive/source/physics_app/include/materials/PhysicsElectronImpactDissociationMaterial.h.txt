#pragma once

#include "FunctorMaterial.h"
#include "PhysicsLookupTable1D.h"

/**
 * Electron-impact O2 dissociation rate owner for the cooling discriminator.
 *
 * Reaction: e + O2 -> e + O + O
 *
 * The supplied table stores k_raw [m^3/(mol s)] versus solved mean electron
 * energy [eV]. Exactly one molar progress functor is produced:
 *
 *   R_diss_O2 = k_raw * (n_e / N_A) * c_O2  [mol/(m^3 s)]
 *
 * This object owns only the reaction-progress lookup. Species and electron-
 * energy projections are separate consumers so the cooling-only discriminator
 * can be assembled without changing heavy-species chemistry.
 */
class PhysicsElectronImpactDissociationMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronImpactDissociationMaterial(const InputParameters & parameters);

protected:
  ADReal interpolateStrict(const ADReal & mean_energy) const;

  const Moose::Functor<ADReal> & _mean_energy;
  const Moose::Functor<ADReal> & _electron_number_density;
  const Moose::Functor<ADReal> & _o2_molar_concentration;
  FileName _rate_table_file;
  PhysicsLookupTable1D _table;
};
