#pragma once

#include "FVDiffusion.h"

/**
 * Diagnostic-only Issue #228 control.
 *
 * On internal faces this uses only the two-cell center-to-center contribution
 * projected onto the face normal. Boundary handling and coefficient
 * interpolation remain the framework FVDiffusion contract. This is not a
 * production discretization recommendation.
 */
class PhysicsFVTwoPointDiffusionControl : public FVDiffusion
{
public:
  static InputParameters validParams();
  PhysicsFVTwoPointDiffusionControl(const InputParameters & params);

protected:
  ADReal computeQpResidual() override;
};
