#pragma once

#include "GeneralPostprocessor.h"

class PhysicsSurfaceChargeState;

/**
 * Exposes global diagnostics owned by PhysicsSurfaceChargeState.
 */
class PhysicsSurfaceChargeStatePostprocessor : public GeneralPostprocessor
{
public:
  static InputParameters validParams();
  PhysicsSurfaceChargeStatePostprocessor(const InputParameters & parameters);

  void initialize() override {}
  void execute() override {}
  PostprocessorValue getValue() const override;

private:
  const PhysicsSurfaceChargeState & _surface_charge_state;
  const MooseEnum _quantity;
};