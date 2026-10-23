#include "PhysicsVariableStateAudit.h"

#include "FEProblemBase.h"
#include "MooseMesh.h"
#include "MooseVariableFieldBase.h"
#include "SystemBase.h"

#include "libmesh/elem.h"
#include "libmesh/numeric_vector.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <unordered_set>
#include <vector>

registerMooseObject("PhysicsApp", PhysicsVariableStateAudit);

InputParameters
PhysicsVariableStateAudit::validParams()
{
  auto params = GeneralUserObject::validParams();
  params.addClassDescription(
      "Prints current and transient-old variable checksums at each execution to audit whether "
      "fixed-point iterations accidentally advance physical time state.");
  params.addRequiredParam<VariableName>("variable", "Solver variable whose state is audited.");
  return params;
}

PhysicsVariableStateAudit::PhysicsVariableStateAudit(const InputParameters & parameters)
  : GeneralUserObject(parameters),
    _variable_name(getParam<VariableName>("variable")),
    _variable(_fe_problem.getVariable(0,
                                      _variable_name,
                                      Moose::VarKindType::VAR_SOLVER,
                                      Moose::VarFieldType::VAR_FIELD_ANY)),
    _last_time(std::numeric_limits<Real>::quiet_NaN()),
    _same_time_execution(0)
{
}

void
PhysicsVariableStateAudit::execute()
{
  auto & sys = _variable.sys();
  const auto & current = sys.solution();
  const auto & old = sys.solutionOld();

  Real old_sum = 0.0;
  Real current_sum = 0.0;
  Real old_sq = 0.0;
  Real current_sq = 0.0;
  Real delta_sq = 0.0;
  Real old_weighted = 0.0;
  Real current_weighted = 0.0;
  unsigned long long n_dofs = 0;

  std::vector<dof_id_type> dofs;
  std::unordered_set<dof_id_type> visited;

  for (const auto * elem : _fe_problem.mesh().getMesh().active_local_element_ptr_range())
  {
    dofs.clear();
    _variable.getDofIndices(elem, dofs);

    for (const auto dof : dofs)
    {
      if (!visited.insert(dof).second)
        continue;

      const Real o = static_cast<Real>(old(dof));
      const Real c = static_cast<Real>(current(dof));
      const Real w = static_cast<Real>(dof + 1);

      old_sum += o;
      current_sum += c;
      old_sq += o * o;
      current_sq += c * c;
      delta_sq += (c - o) * (c - o);
      old_weighted += w * o;
      current_weighted += w * c;
      ++n_dofs;
    }
  }

  sys.comm().sum(old_sum);
  sys.comm().sum(current_sum);
  sys.comm().sum(old_sq);
  sys.comm().sum(current_sq);
  sys.comm().sum(delta_sq);
  sys.comm().sum(old_weighted);
  sys.comm().sum(current_weighted);
  sys.comm().sum(n_dofs);

  const Real time = _fe_problem.time();
  const Real scale = std::max<Real>({1.0, std::abs(time), std::abs(_last_time)});
  if (std::isfinite(_last_time) && std::abs(time - _last_time) <= 1.0e-14 * scale)
    ++_same_time_execution;
  else
    _same_time_execution = 0;
  _last_time = time;

  _console << std::setprecision(17)
           << "STATE_AUDIT variable=" << _variable_name
           << " time_s=" << time
           << " dt_s=" << _fe_problem.dt()
           << " same_time_execution=" << _same_time_execution
           << " n_dofs=" << n_dofs
           << " old_sum=" << old_sum
           << " old_l2=" << std::sqrt(old_sq)
           << " old_weighted=" << old_weighted
           << " current_sum=" << current_sum
           << " current_l2=" << std::sqrt(current_sq)
           << " current_weighted=" << current_weighted
           << " current_minus_old_l2=" << std::sqrt(delta_sq)
           << std::endl;
}
