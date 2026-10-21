#pragma once

#include "FunctorMaterial.h"

/**
 * Electron absorbing-wall flux suppressed by a plasma-side, adjacent-cell sheath drop.
 *
 * On a wall face,
 *
 *   Delta phi = max(E_n d_perp, 0)
 *   Gamma_e   = s * n_e * vbar_e/4 * exp(-Delta phi / T_e)
 *
 * where E_n = E.n_out, E=-grad(phi), d_perp is the normal distance from the
 * wall-face centroid to the plasma-side adjacent-element centroid, and
 * T_e=(2/3)<epsilon_e> in eV.  E_n d_perp is the first-order reconstruction of
 * phi_adjacent - phi_wall used by the Issue #395 diagnostic.
 */
class PhysicsElectronAdjacentSheathWallFluxMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronAdjacentSheathWallFluxMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _electron_density;
  const Moose::Functor<ADReal> & _mean_energy;
  const Moose::Functor<ADReal> & _potential;
  const Real _sticking;
  const bool _use_element_gradient_for_potential;
};
