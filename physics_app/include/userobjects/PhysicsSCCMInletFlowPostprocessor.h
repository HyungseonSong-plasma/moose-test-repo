#pragma once

#include "GeneralPostprocessor.h"

/**
 * Derived inlet mass-flux magnitude or speed from the accepted standard-state
 * SCCM mass-flow rate and the mesh-measured inlet area.
 *
 * These are scalar magnitudes. The flow BC independently owns the inlet
 * direction and applies the signed conservation-law residual.
 */
class PhysicsSCCMInletFlowPostprocessor : public GeneralPostprocessor
{
public:
  static InputParameters validParams();
  PhysicsSCCMInletFlowPostprocessor(const InputParameters & parameters);

  void initialize() override {}
  void execute() override {}
  PostprocessorValue getValue() const override;

private:
  const Real _mdot;
  const Real _inlet_density;
  const MooseEnum _quantity;
  const PostprocessorValue & _inlet_area;
};
