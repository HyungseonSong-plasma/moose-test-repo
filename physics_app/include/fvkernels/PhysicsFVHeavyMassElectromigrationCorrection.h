#pragma once

#include "FVFluxKernel.h"

#include <vector>

/**
 * Conservative heavy-species mass-average electromigration correction.
 *
 * For every internal face, this kernel reconstructs the provisional direct
 * charged-heavy migration mass flux using the same electric-field, mobility,
 * density, and advected interpolation contract as PhysicsFVElectrostaticDrift:
 *
 *   J_direct,n = sum_i rho_f * w_i,up * z_i * mu_i,f * (E_f . n)
 *
 * The common correction mass flux is
 *
 *   J_corr,n = -J_direct,n
 *
 * and species k receives
 *
 *   j_k,corr,n = w_k,up(corr) * J_corr,n.
 *
 * If all heavy-species mass fractions use this kernel with identical
 * parameters and sum_k w_k = 1 in each donor cell, then
 *
 *   sum_k j_k,corr,n = -J_direct,n
 *
 * to discrete interpolation precision, so the total heavy-species
 * electromigration mass flux is conservative face-by-face.
 *
 * Physical wall losses are handled by wall boundary conditions; this kernel
 * should normally avoid external wall boundaries.
 */
class PhysicsFVHeavyMassElectromigrationCorrection : public FVFluxKernel
{
public:
  static InputParameters validParams();

  PhysicsFVHeavyMassElectromigrationCorrection(
      const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _rho;

  const std::vector<MooseFunctorName> _ion_mass_fraction_names;
  const std::vector<MooseFunctorName> _ion_mobility_names;
  const std::vector<Real> _ion_charges;

  std::vector<const Moose::Functor<ADReal> *> _ion_mass_fractions;
  std::vector<const Moose::Functor<ADReal> *> _ion_mobilities;

  Moose::FV::InterpMethod _advected_interp_method;
};
