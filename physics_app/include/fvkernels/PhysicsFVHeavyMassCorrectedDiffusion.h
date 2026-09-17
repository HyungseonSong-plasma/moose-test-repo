#pragma once

#include "FVFluxKernel.h"

#include <vector>

/**
 * Conservative mixture-averaged heavy-species diffusion flux.
 *
 * Provisional species flux:
 *   J_k^raw = -rho D_km [grad(w_k) + (w_k/Mn) grad(Mn)]
 *
 * Mass-average correction:
 *   J_k = J_k^raw - w_k sum_j J_j^raw
 *
 * With sum_j w_j = 1, the complete heavy-species set satisfies
 *   sum_j J_j = 0
 * face-by-face by construction. External faces are left to surface-reaction
 * boundary conditions; this kernel owns internal/bulk diffusion only.
 */
class PhysicsFVHeavyMassCorrectedDiffusion : public FVFluxKernel
{
public:
  static InputParameters validParams();
  PhysicsFVHeavyMassCorrectedDiffusion(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _rho;
  const Moose::Functor<ADReal> & _mean_molar_mass;
  const std::vector<MooseFunctorName> _mass_fraction_names;
  const std::vector<MooseFunctorName> _diffusivity_names;
  const unsigned int _species_index;

  std::vector<const Moose::Functor<ADReal> *> _mass_fractions;
  std::vector<const Moose::Functor<ADReal> *> _diffusivities;
};
