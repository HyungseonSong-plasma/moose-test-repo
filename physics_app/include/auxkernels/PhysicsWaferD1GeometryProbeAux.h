#pragma once

#include "AuxKernel.h"
#include "MooseFunctorArguments.h"

/**
 * Issue #397 D1: inspect the same plasma-sided FaceInfo used by
 * PhysicsLowerDSurfaceCurrent, without changing any governing residual.
 *
 * Reports signed plasma-outward normal, sided adjacent-cell electric field,
 * normal wall-to-cell distance, and raw owner sign for each lower-D face.
 * The E field and distance deliberately use the production adjacent-sheath
 * reconstruction and are observational (not an independent reference).
 */
class PhysicsWaferD1GeometryProbeAux : public AuxKernel
{
public:
  static InputParameters validParams();
  PhysicsWaferD1GeometryProbeAux(const InputParameters & parameters);

protected:
  Real computeValue() override;

private:
  const Moose::Functor<ADReal> & _surface_current_density;
  const Moose::Functor<ADReal> & _potential;
  const MooseEnum _component;
};
