#pragma once

#include "Action.h"

/**
 * User-facing composition layer for plasma closure materials.
 *
 * This Action intentionally keeps the underlying C++ materials separate while
 * exposing one concise input block for electron transport, electron kinetics,
 * heavy-particle transport, and electrostatic charge closure.
 */
class PlasmaClosuresAction : public Action
{
public:
  static InputParameters validParams();
  PlasmaClosuresAction(const InputParameters & parameters);

  void act() override;

private:
  void validateConfiguration() const;
};
