#pragma once

#include "INSFVRhieChowInterpolator.h"

/**
 * Diagnostic-only Rhie-Chow interpolator used to attribute setup memory.
 *
 * It preserves the standard MOOSE constructor and initialSetup path but skips
 * execute(), which otherwise gathers momentum residual/Jacobian AD data even
 * when velocity_interp_method=average.  It must never be used for a physical
 * timestep or promoted to production.
 */
class PhysicsDiagnosticNoGatherRhieChowInterpolator : public INSFVRhieChowInterpolator
{
public:
  static InputParameters validParams();
  PhysicsDiagnosticNoGatherRhieChowInterpolator(const InputParameters & parameters);

  void execute() override {}
};
