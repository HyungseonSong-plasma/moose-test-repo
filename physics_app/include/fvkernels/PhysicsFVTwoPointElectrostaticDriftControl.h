#pragma once

#include "PhysicsFVElectrostaticDrift.h"

/**
 * Diagnostic-only Issue #228 control.
 *
 * Uses the same mobility, carrier, charge sign, and upwind transported state as
 * PhysicsFVElectrostaticDrift, but replaces the corrected face-gradient normal
 * component by the two-cell center-to-center normal projection. This is not a
 * production model; it isolates the effect of the non-orthogonal gradient
 * reconstruction on electron drift.
 */
class PhysicsFVTwoPointElectrostaticDriftControl : public PhysicsFVElectrostaticDrift
{
public:
  static InputParameters validParams();
  PhysicsFVTwoPointElectrostaticDriftControl(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;
};
