#pragma once

#include "FVQpFluxBC.h"

/**
 * Generic finite-volume Neumann flux adapter that evaluates the supplied
 * functor on the adjacent cell rather than on the boundary face.
 *
 * MOOSE's standard FVFunctorNeumannBC evaluates its functor with a FaceArg.
 * On a Dirichlet face an FV variable functor therefore returns the imposed
 * boundary value. Some closures instead require the plasma-side/cell state.
 *
 * This object owns only that evaluation-location mechanic. It contains no
 * sheath, plasma, species, or energy model semantics.
 */
class PhysicsFVCellFunctorNeumannBC : public FVQpFluxBC
{
public:
  static InputParameters validParams();
  PhysicsFVCellFunctorNeumannBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _functor;
  const Moose::Functor<ADReal> & _factor;
};
