#pragma once

#include "AuxKernel.h"


class PhysicsBackgroundDensity : public AuxKernel
{
public:
  PhysicsBackgroundDensity(const InputParameters & parameters);

  static InputParameters validParams();

  virtual Real computeValue() override;

protected:

  /// Coupled background gas temperature variable
  const VariableValue & _T_gas;
  const VariableValue & _p_gas;
};