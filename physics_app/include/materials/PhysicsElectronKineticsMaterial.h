#pragma once

#include "FunctorMaterial.h"
#include "PhysicsLookupTable1D.h"

#include <cstddef>
#include <string>
#include <vector>

/**
 * Multi-reaction electron-impact kinetics owner.
 *
 * Every reaction uses the same mean-electron-energy coordinate and electron
 * number density, but may use a different target concentration and rate table.
 * Each published reaction-progress functor is
 *
 *   R_k = k_raw(mean_energy) * (n_e / N_A) * c_target
 *
 * in mol/(m^3 s).
 */
class PhysicsElectronKineticsMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronKineticsMaterial(const InputParameters & parameters);

protected:
  ADReal interpolateStrict(const ADReal & coordinate, std::size_t reaction_index) const;

  const Moose::Functor<ADReal> & _electron_mean_energy;
  const Moose::Functor<ADReal> & _electron_number_density;

  const std::vector<FileName> _rate_table_files;
  const std::vector<MooseFunctorName> _target_molar_concentration_names;
  const std::vector<std::string> _reaction_progress_names;

  std::vector<const Moose::Functor<ADReal> *> _target_molar_concentrations;
  std::vector<PhysicsLookupTable1D> _tables;
};
