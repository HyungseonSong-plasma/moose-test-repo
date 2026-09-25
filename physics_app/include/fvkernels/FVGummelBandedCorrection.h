#pragma once

#include "FVElementalKernel.h"

/**
 * Nonlocal banded Gummel correction for the Poisson block.
 *
 * The kernel applies a row of a measured dimensionless electron-response
 * matrix W to delta_phi = phi - phi_anchor:
 *
 *   R_corr,i = beta_i * sum_j W_ij * delta_phi_j,
 *
 * beta_i = (e/eps0) * n_e / VTe.
 *
 * The supplied W is row-sum preserving, so a uniform potential shift is in the
 * null space.  The correction also vanishes exactly at a converged Gummel
 * fixed point where phi == phi_anchor.
 */
class FVGummelBandedCorrection : public FVElementalKernel
{
public:
  static InputParameters validParams();
  FVGummelBandedCorrection(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

private:
  const Elem * offsetElem(const Elem * start, int offset) const;
  unsigned int rowIndex(const Elem * elem) const;

  const Moose::Functor<ADReal> & _anchor;
  const Moose::Functor<ADReal> & _beta;
  const std::vector<Real> _matrix;
  const unsigned int _n_cells;
  const unsigned int _bandwidth;
  const Real _xmin;
  const Real _dx;
};
