#pragma once

#include "FVElementalKernel.h"

/**
 * Applies a signed physical electron number source to the normalized electron
 * continuity equation.
 *
 * The electron state is n_e_phys = n_ref * n_e_hat.  If S_e is the signed
 * physical electron number source [1/(m^3 s)], the normalized equation uses
 *
 *   S_e_hat = S_e / n_ref [1/s].
 *
 * Positive S_e means electron production and negative S_e means electron loss.
 * As for other FV source kernels, the residual contribution is -S_e_hat.
 *
 * This kernel intentionally consumes a source functor rather than recomputing a
 * reaction rate.  Electron, heavy-species, and later electron-energy source
 * owners must therefore reuse one upstream canonical reaction progress R_r.
 */
class QPXFVElectronReactionSource : public FVElementalKernel
{
public:
  static InputParameters validParams();
  QPXFVElectronReactionSource(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _number_source;
  const Real _n_ref;
};
