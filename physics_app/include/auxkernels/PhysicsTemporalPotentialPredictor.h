#pragma once

#include "AuxKernel.h"

class PhysicsTemporalPotentialPredictor : public AuxKernel
{
public:
  PhysicsTemporalPotentialPredictor(const InputParameters & parameters);

  static InputParameters validParams();

protected:
  virtual Real computeValue() override;

  const VariableValue & _u_old;
  const VariableValue & _u_older;
  const Real _alpha;
  const unsigned int _start_step;
};
