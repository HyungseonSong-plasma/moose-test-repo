#pragma once

#include "PhysicsBase.h"

#include <string>
#include <vector>

/**
 * Provides shared validation for plasma physics inputs.
 *
 * Derived physics classes decide which equations to build.
 */
class PlasmaInterface : public PhysicsBase
{
public:
  static InputParameters validParams();

protected:
  explicit PlasmaInterface(const InputParameters & parameters);

  void validateSpeciesInputs(const std::vector<std::string> & finite_element_species,
                             const std::vector<std::string> & finite_volume_species,
                             const std::vector<VariableName> & variables) const;

  // Reject repeated existing FEM operators on the same solver variable.
  // This prevents an explicit native Kernel and a Physics-generated Kernel
  // of the same type from silently adding the same residual twice.
  void requireUniqueFEKernel(const std::string & type, const VariableName & variable) const;

  void validateExistingSpeciesVariables(const std::vector<std::string> & finite_element_species,
                                        const std::vector<std::string> & finite_volume_species,
                                        const std::vector<VariableName> & variables) const;
};
