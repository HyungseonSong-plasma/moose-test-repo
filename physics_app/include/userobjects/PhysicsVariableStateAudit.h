#pragma once

#include "GeneralUserObject.h"

class MooseVariableFieldBase;

/**
 * Diagnostic user object for auditing transient state handling across repeated
 * solves at the same physical time (for example MultiApp fixed-point loops).
 *
 * At every execution it prints variable-specific checksums and L2 norms for
 * the current solution and the transient old solution.  The old-state values
 * must remain invariant across all fixed-point iterations belonging to one
 * physical timestep.
 */
class PhysicsVariableStateAudit : public GeneralUserObject
{
public:
  static InputParameters validParams();
  PhysicsVariableStateAudit(const InputParameters & parameters);

  void initialize() override {}
  void execute() override;
  void finalize() override {}

private:
  const VariableName _variable_name;
  MooseVariableFieldBase & _variable;
  Real _last_time;
  unsigned int _same_time_execution;
};
