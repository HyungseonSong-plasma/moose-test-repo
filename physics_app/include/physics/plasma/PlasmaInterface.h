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

  void validateExistingSpeciesVariables(const std::vector<std::string> & finite_element_species,
                                        const std::vector<std::string> & finite_volume_species,
                                        const std::vector<VariableName> & variables) const;
};
