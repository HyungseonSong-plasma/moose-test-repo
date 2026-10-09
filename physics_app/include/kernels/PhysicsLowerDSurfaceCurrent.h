#pragma once

#include "ADKernel.h"

/**
 * Evolves a lower-dimensional surface-charge variable from a signed current
 * density functor evaluated on the associated higher-dimensional FV face.
 *
 * This kernel supplies only the source term
 *
 *   R_sigma,source = - integral_Gamma test * j_to_surface dA
 *
 * and is intended to be paired with ADTimeDerivative on sigma_s so that
 *
 *   d(sigma_s)/dt = j_to_surface.
 *
 * The lower-dimensional element must have an interior_parent() created from
 * the plasma-dielectric sideset (for example with
 * LowerDBlockFromSidesetGenerator).  The current functor is always evaluated
 * on that parent/plasma side of the corresponding FV FaceInfo.
 */
class PhysicsLowerDSurfaceCurrent : public ADKernel
{
public:
  static InputParameters validParams();

  PhysicsLowerDSurfaceCurrent(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

private:
  const Moose::Functor<ADReal> & _surface_current_density;
};
