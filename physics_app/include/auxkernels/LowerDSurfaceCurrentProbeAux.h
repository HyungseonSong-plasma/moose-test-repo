// Canonical lower-dimensional surface current observation only. No legacy alias.
// Its FaceArg and plasma-side ownership checks reproduce the pinned
// historical AuxKernel diagnostic, without adding a solver residual.
#pragma once

#include "AuxKernel.h"
#include "MooseFunctorArguments.h"

/** Observe the exact higher-D face-current functor used by PhysicsLowerDSurfaceCurrent.
 * Runs on wafer_surface lower-dimensional elements, independently of sigma time derivative.
 */
class LowerDSurfaceCurrentProbeAux : public AuxKernel
{
public:
  static InputParameters validParams();
  LowerDSurfaceCurrentProbeAux(const InputParameters & parameters);
protected:
  Real computeValue() override;
private:
  const Moose::Functor<ADReal> & _surface_current_density;
};
