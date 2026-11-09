#pragma once

#include "PlasmaInterface.h"

namespace Plasma
{

/**
 * Validates existing maxwell simulation inputs without adding solver objects.
 */
class MaxwellPhysics : public PlasmaInterface
{
public:
  static InputParameters validParams();
  explicit MaxwellPhysics(const InputParameters & parameters);

private:
  void checkIntegrity() const override;
};

}
