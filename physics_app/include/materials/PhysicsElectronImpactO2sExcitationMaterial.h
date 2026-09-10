#pragma once

#include "FunctorMaterial.h"

/**
 * Canonical Stage-3 rate owner for e + O2 -> e + O2(a1Delta_g).
 *
 * R_O2s = k_const * (n_e / N_A) * c_O2 [mol/(m^3 s)]
 *
 * The frozen constant surrogate is a user-authorized modeling decision at the
 * accepted reference electron state. Heavy-source projection is owned by a
 * separate consumer. This object intentionally owns no electron-particle or
 * electron-energy source; the latter remains deferred to #26 E8.
 */
class PhysicsElectronImpactO2sExcitationMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronImpactO2sExcitationMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _electron_number_density;
  const Moose::Functor<ADReal> & _o2_molar_concentration;
};
