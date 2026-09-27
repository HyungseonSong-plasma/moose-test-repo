#pragma once

#include "Action.h"

/**
 * Builds the electron-subsystem <-> Poisson fixed-point coupling used by a
 * Gummel iteration.
 *
 * The Action intentionally does not create or select electron equations.
 * The current application may solve drift-diffusion, density/energy,
 * density/momentum/energy, or another electron model.  The only contract is
 * the variable mapping exchanged with the Poisson sub-application.
 */
class GummelIterationAction : public Action
{
public:
  static InputParameters validParams();
  GummelIterationAction(const InputParameters & parameters);

  void act() override;

private:
  void checkVariableMaps() const;
};
