#pragma once

#include "PhysicsFVElectrostaticDrift.h"

/**
 * Diagnostic-only Issue #228 control.
 *
 * Retains the production multidimensional face gradient, but limits the
 * non-orthogonal correction in the face-normal component to
 *
 *   |g_corr,n| <= correction_cap_ratio * |g_central,n|.
 *
 * correction_cap_ratio = 0 recovers the two-point normal gradient;
 * correction_cap_ratio = 1 prevents the correction from exceeding the
 * central term magnitude and therefore prevents a pure correction-driven
 * sign reversal. This is a numerical discriminator, not accepted production
 * physics.
 */
class PhysicsFVLimitedElectrostaticDriftControl : public PhysicsFVElectrostaticDrift
{
public:
  static InputParameters validParams();
  PhysicsFVLimitedElectrostaticDriftControl(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Real _correction_cap_ratio;
};
