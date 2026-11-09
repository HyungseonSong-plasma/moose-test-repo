#pragma once

#include "PhysicsBase.h"

/**
 * Issue #402 G1 observation-only bridge from Plasma DSL species lists to
 * existing FEM/FV continuity variables.
 *
 * It deliberately does not generate variables, equations, sources or BCs.
 * This permits native syntax/ABI/variable-family validation against the
 * immutable S6 input without changing the science.
 */
class PlasmaSpeciesContinuityPhysics : public PhysicsBase
{
public:
  static InputParameters validParams();
  PlasmaSpeciesContinuityPhysics(const InputParameters & parameters);

private:
  void checkIntegrity() const override;
};
