#pragma once

#include "Predictor.h"

#include <vector>

/**
 * Predictor that overwrites selected nonlinear variables with values stored in
 * same-mesh auxiliary variables immediately before the nonlinear solve.
 *
 * This is used to inject a predictor MultiApp endpoint as a Newton initial guess
 * without modifying the transient old/older solution states used by time
 * derivatives.
 */
class PhysicsTransferredSolutionPredictor : public Predictor
{
public:
  static InputParameters validParams();
  PhysicsTransferredSolutionPredictor(const InputParameters & parameters);

  bool shouldApply() override;
  void apply(NumericVector<Number> & sln) override;

protected:
  const std::vector<VariableName> _source_variables;
  const std::vector<VariableName> _target_variables;
  Real & _last_applied_time;
};
