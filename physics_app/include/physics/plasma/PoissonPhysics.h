#pragma once

#include "PlasmaInterface.h"

namespace Plasma
{

/**
 * Validates existing poisson simulation inputs without adding solver objects.
 */
class PoissonPhysics : public PlasmaInterface
{
public:
  static InputParameters validParams();
  explicit PoissonPhysics(const InputParameters & parameters);

private:
  void checkIntegrity() const override;
};

}
