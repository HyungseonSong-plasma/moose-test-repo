#pragma once

#include "AuxKernel.h"
#include "MooseFunctorArguments.h"

/** Observe the exact higher-D face-current functor used by PhysicsLowerDSurfaceCurrent.
 * Runs on wafer_surface lower-dimensional elements, independently of sigma time derivative.
 */
class PhysicsLowerDSurfaceCurrentProbeAux : public AuxKernel
{
public:
  static InputParameters validParams();
  PhysicsLowerDSurfaceCurrentProbeAux(const InputParameters & parameters);
protected:
  Real computeValue() override;
private:
  const Moose::Functor<ADReal> & _surface_current_density;
};
