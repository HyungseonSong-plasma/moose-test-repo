#pragma once

#include "TimeStepper.h"
#include "PostprocessorInterface.h"

/**
 * Physical timestep controller driven by predictor/corrector fast-block
 * fixed-point iteration counts.
 *
 * Successful steps:
 *   max(pred_its, corr_its) < grow_below_iterations   -> dt *= grow_factor
 *   max(pred_its, corr_its) > shrink_above_iterations -> dt *= shrink_factor
 *   otherwise                                           -> hold dt
 *
 * Failed steps use the standard TimeStepper cutback_factor_at_failure.
 */
class PhysicsFastFixedPointAdaptiveDT : public TimeStepper, public PostprocessorInterface
{
public:
  static InputParameters validParams();
  PhysicsFastFixedPointAdaptiveDT(const InputParameters & parameters);

protected:
  Real computeInitialDT() override;
  Real computeDT() override;

  const PostprocessorValue & _predictor_iterations;
  const PostprocessorValue & _corrector_iterations;

  const Real _initial_dt;
  const Real _grow_factor;
  const Real _shrink_factor;
  const Real _grow_below_iterations;
  const Real _shrink_above_iterations;
};
