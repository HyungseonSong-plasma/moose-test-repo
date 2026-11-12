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
  void addSolverVariables() override;
  void addInitialConditions() override;
  void checkIntegrity() const override;
  void addFEKernels() override;
  void addFEBCs() override;
  bool _created_potential_variable = false;
};

}
