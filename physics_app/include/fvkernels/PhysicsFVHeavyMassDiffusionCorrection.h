#pragma once

#include "FVFluxKernel.h"

#include <vector>

/**
 * Mass-average correction for mixture-averaged heavy-species diffusion.
 *
 * The provisional species flux is reconstructed as
 *
 *   J_k^raw = -rho D_km [grad(w_k) + (w_k/Mn) grad(Mn)].
 *
 * This kernel adds, to solved species k,
 *
 *   J_k^correction = -w_k sum_j J_j^raw.
 *
 * Therefore the corrected seven-species oxygen flux satisfies
 *
 *   sum_k J_k^corrected = 0
 *
 * face-by-face when sum_k w_k = 1. O2 may be an algebraically constrained
 * species: its corrected flux is then exactly the negative sum of the solved
 * species corrected fluxes.
 */
class PhysicsFVHeavyMassDiffusionCorrection : public FVFluxKernel
{
public:
  static InputParameters validParams();

  PhysicsFVHeavyMassDiffusionCorrection(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _rho;
  const Moose::Functor<ADReal> & _mean_molar_mass;

  const std::vector<MooseFunctorName> _mass_fraction_names;
  const std::vector<MooseFunctorName> _diffusivity_names;

  std::vector<const Moose::Functor<ADReal> *> _mass_fractions;
  std::vector<const Moose::Functor<ADReal> *> _diffusivities;
};
