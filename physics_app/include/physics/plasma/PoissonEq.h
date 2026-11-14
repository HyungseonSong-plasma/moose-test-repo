#pragma once

#include "PlasmaInterface.h"

namespace Plasma
{

/**
 * Owns or reuses an FEM potential state and generates activated Poisson operators.
 */
class PoissonEq : public PlasmaInterface
{
public:
  static InputParameters validParams();
  explicit PoissonEq(const InputParameters & parameters);

private:
  void addSolverVariables() override;
  void addInitialConditions() override;
  void checkIntegrity() const override;
  void addFEKernels() override;
  void addFEBCs() override;
  bool _created_potential_variable = false;
};

}
