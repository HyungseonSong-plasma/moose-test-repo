#pragma once

#include "PlasmaInterface.h"

namespace Plasma
{

/**
 * Checks the species and solver variables used by a continuity equation.
 *
 * The existing equations remain responsible for the simulation.
 */
class ContinuityPhysics : public PlasmaInterface
{
public:
  static InputParameters validParams();
  explicit ContinuityPhysics(const InputParameters & parameters);

private:
  void checkIntegrity() const override;
  void addFEKernels() override;
};

}
