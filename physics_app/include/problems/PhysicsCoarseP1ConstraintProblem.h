#pragma once

#include "FEProblem.h"
#include "libmesh/system.h"

#include <memory>
#include <string>
#include <vector>

class PhysicsCoarseP1ConstraintProblem : public FEProblem
{
public:
  static InputParameters validParams();

  PhysicsCoarseP1ConstraintProblem(const InputParameters & parameters);
  ~PhysicsCoarseP1ConstraintProblem() override;

  void init() override;

private:
  std::string _constrained_variable;
  std::vector<dof_id_type> _secondary_nodes;
  std::vector<dof_id_type> _primary_nodes_a;
  std::vector<dof_id_type> _primary_nodes_b;
  std::unique_ptr<libMesh::System::Constraint> _coarse_p1_constraint;
};
