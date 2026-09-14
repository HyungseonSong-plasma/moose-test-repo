#pragma once

#include "PhysicsFVElectrostaticDrift.h"

#include <vector>

/**
 * Diagnostic-only wrapper around PhysicsFVElectrostaticDrift.
 *
 * The production residual is delegated to the accepted parent implementation.
 * When both cells adjacent to an internal face are listed in
 * diagnostic_element_ids, the exact face-normal electrostatic quantities used
 * by the kernel are printed for Issue #228 forensic analysis.
 */
class PhysicsFVElectrostaticDriftDiagnostic : public PhysicsFVElectrostaticDrift
{
public:
  static InputParameters validParams();
  PhysicsFVElectrostaticDriftDiagnostic(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;
  bool probeFace() const;

  const std::vector<unsigned int> _diagnostic_element_ids;
};
