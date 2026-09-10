#pragma once

#include "FunctorMaterial.h"
#include "PhysicsLookupTable1D.h"

#include <string>

/**
 * Reusable strict mean-energy electron-impact molar reaction-progress owner.
 *
 * The supplied two-column table stores k_raw [m^3/(mol s)] versus solved mean
 * electron energy [eV]. This object evaluates kinetics exactly once and publishes
 * one named molar progress functor
 *
 *   R_k = k_raw(mean_en) * (n_e / N_A) * c_target  [mol/(m^3 s)].
 *
 * Downstream particle, heavy-species and electron-energy projections must consume
 * this functor and must not independently interpolate the kinetic table.
 */
class PhysicsElectronImpactRateMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronImpactRateMaterial(const InputParameters & parameters);

protected:
  ADReal interpolateStrict(const ADReal & mean_energy) const;

  const Moose::Functor<ADReal> & _mean_energy;
  const Moose::Functor<ADReal> & _electron_number_density;
  const Moose::Functor<ADReal> & _target_molar_concentration;
  const FileName _rate_table_file;
  const std::string _reaction_progress_name;
  PhysicsLookupTable1D _table;
};
