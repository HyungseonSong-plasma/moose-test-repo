#pragma once

#include "PhysicsBase.h"

/**
 * Checks that each plasma species uses an existing solver variable of the correct type.
 * Does not create variables or equations.
 */
class PlasmaSpeciesVariableCheckPhysics : public PhysicsBase
{
public:
  static InputParameters validParams();
  PlasmaSpeciesVariableCheckPhysics(const InputParameters & parameters);

private:
  void checkIntegrity() const override;
};
