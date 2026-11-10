#pragma once

#include "PlasmaInterface.h"

namespace Plasma
{

/**
 * Validates existing chemistry simulation inputs without adding solver objects.
 */
class ChemistryPhysics : public PlasmaInterface
{
public:
  static InputParameters validParams();
  explicit ChemistryPhysics(const InputParameters & parameters);

private:
  void checkIntegrity() const override;
  void addFunctorMaterials() override;
};

}
