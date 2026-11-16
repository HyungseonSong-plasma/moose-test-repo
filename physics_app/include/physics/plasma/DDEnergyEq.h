#pragma once

#include "PlasmaInterface.h"

namespace Plasma
{

/**
 * Validates existing energy simulation inputs without adding solver objects.
 */
class DDEnergyEq : public PlasmaInterface
{
public:
  static InputParameters validParams();
  explicit DDEnergyEq(const InputParameters & parameters);

private:
  void addSolverVariables() override;
  void addInitialConditions() override;
  void checkIntegrity() const override;
  void addFEKernels() override;
  void addFEBCs() override;
  void addFunctorMaterials() override;
  bool _created_energy_variable = false;
};

}
