#pragma once

#include "PlasmaInterface.h"

#include <map>
#include <string>
#include <vector>

namespace Plasma
{

/**
 * Validates plasma species and their resolved solver variables.
 *
 * Generates supported FEM drift-diffusion kernels; FV kernels remain external.
 * Shares species and duplicate-operator checks with other plasma Physics.
 */
class DDContinuityEq : public PlasmaInterface
{
public:
  static InputParameters validParams();
  explicit DDContinuityEq(const InputParameters & parameters);

private:
  void checkIntegrity() const override;
  void addSolverVariables() override;
  void addInitialConditions() override;
  void addFEKernels() override;
  void addFEBCs() override;
  void addFunctorMaterials() override;

  std::vector<std::string> _fem_species;
  std::vector<std::string> _fvm_species;
  std::map<std::string, Real> _fem_initial_number_densities;
  std::map<std::string, Real> _fvm_initial_number_densities;
};

}
