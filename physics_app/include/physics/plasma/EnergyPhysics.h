#pragma once

#include "PlasmaInterface.h"

namespace Plasma
{

/**
 * Validates existing energy simulation inputs without adding solver objects.
 */
class EnergyPhysics : public PlasmaInterface
{
public:
  static InputParameters validParams();
  explicit EnergyPhysics(const InputParameters & parameters);

private:
  void checkIntegrity() const override;
};

}
