#include "PhysicsCoarseP1ConstraintProblem.h"

#include "NonlinearSystemBase.h"

#include "libmesh/dof_map.h"
#include "libmesh/mesh_base.h"
#include "libmesh/node.h"

registerMooseObject("PhysicsApp", PhysicsCoarseP1ConstraintProblem);

namespace
{
class CoarseP1MidpointConstraint : public libMesh::System::Constraint
{
public:
  CoarseP1MidpointConstraint(libMesh::System & system,
                             std::string variable,
                             std::vector<dof_id_type> secondary_nodes,
                             std::vector<dof_id_type> primary_nodes_a,
                             std::vector<dof_id_type> primary_nodes_b)
    : _system(system),
      _variable(std::move(variable)),
      _secondary_nodes(std::move(secondary_nodes)),
      _primary_nodes_a(std::move(primary_nodes_a)),
      _primary_nodes_b(std::move(primary_nodes_b))
  {
  }

  void constrain() override
  {
    const auto variable_number = _system.variable_number(_variable);
    auto & mesh = _system.get_mesh();
    auto & dof_map = _system.get_dof_map();

    for (std::size_t i = 0; i < _secondary_nodes.size(); ++i)
    {
      const auto secondary_id = _secondary_nodes[i];
      const auto primary_a_id = _primary_nodes_a[i];
      const auto primary_b_id = _primary_nodes_b[i];

      const auto * secondary = mesh.query_node_ptr(secondary_id);
      const auto * primary_a = mesh.query_node_ptr(primary_a_id);
      const auto * primary_b = mesh.query_node_ptr(primary_b_id);

      if (!secondary || !primary_a || !primary_b)
        libmesh_error_msg("Coarse-P1 constraint references a node that is not present in the mesh: "
                          << secondary_id << " <- (" << primary_a_id << ", " << primary_b_id
                          << ")");

      const auto secondary_dof =
          secondary->dof_number(_system.number(), variable_number, /*component=*/0);
      const auto primary_a_dof =
          primary_a->dof_number(_system.number(), variable_number, /*component=*/0);
      const auto primary_b_dof =
          primary_b->dof_number(_system.number(), variable_number, /*component=*/0);

      libMesh::DofConstraintRow row;
      row[primary_a_dof] = 0.5;
      row[primary_b_dof] = 0.5;

      // Exact homogeneous algebraic constraint:
      //   phi_mid = 0.5 * phi_a + 0.5 * phi_b
      // This is processed by libMesh in the same DofMap constraint machinery used
      // for hanging nodes, before matrix/vector allocation and nonlinear solves.
      dof_map.add_constraint_row(secondary_dof, row, /*forbid_constraint_overwrite=*/true);
    }
  }

private:
  libMesh::System & _system;
  const std::string _variable;
  const std::vector<dof_id_type> _secondary_nodes;
  const std::vector<dof_id_type> _primary_nodes_a;
  const std::vector<dof_id_type> _primary_nodes_b;
};
}

InputParameters
PhysicsCoarseP1ConstraintProblem::validParams()
{
  InputParameters params = FEProblem::validParams();
  params.addRequiredParam<std::string>(
      "coarse_p1_variable", "Nodal P1 variable whose refinement midpoint DOFs are constrained.");
  params.addRequiredParam<std::vector<dof_id_type>>(
      "coarse_p1_secondary_nodes", "Refinement midpoint node ids to constrain.");
  params.addRequiredParam<std::vector<dof_id_type>>(
      "coarse_p1_primary_nodes_a", "First coarse-edge endpoint for each midpoint.");
  params.addRequiredParam<std::vector<dof_id_type>>(
      "coarse_p1_primary_nodes_b", "Second coarse-edge endpoint for each midpoint.");
  params.addClassDescription(
      "FEProblem that attaches exact libMesh DofMap midpoint constraints before system init so a "
      "refined transport mesh can retain the original coarse P1 potential space.");
  return params;
}

PhysicsCoarseP1ConstraintProblem::PhysicsCoarseP1ConstraintProblem(
    const InputParameters & parameters)
  : FEProblem(parameters),
    _constrained_variable(getParam<std::string>("coarse_p1_variable")),
    _secondary_nodes(getParam<std::vector<dof_id_type>>("coarse_p1_secondary_nodes")),
    _primary_nodes_a(getParam<std::vector<dof_id_type>>("coarse_p1_primary_nodes_a")),
    _primary_nodes_b(getParam<std::vector<dof_id_type>>("coarse_p1_primary_nodes_b"))
{
  if (_secondary_nodes.empty())
    paramError("coarse_p1_secondary_nodes", "At least one midpoint constraint is required.");

  if (_primary_nodes_a.size() != _secondary_nodes.size() ||
      _primary_nodes_b.size() != _secondary_nodes.size())
    paramError("coarse_p1_secondary_nodes",
               "secondary, primary-a, and primary-b node lists must have identical lengths.");
}

PhysicsCoarseP1ConstraintProblem::~PhysicsCoarseP1ConstraintProblem() = default;

void
PhysicsCoarseP1ConstraintProblem::init()
{
  if (!_coarse_p1_constraint)
  {
    auto & system = getNonlinearSystemBase(/*nl_sys_num=*/0).system();
    _coarse_p1_constraint = std::make_unique<CoarseP1MidpointConstraint>(system,
                                                                         _constrained_variable,
                                                                         _secondary_nodes,
                                                                         _primary_nodes_a,
                                                                         _primary_nodes_b);
    system.attach_constraint_object(*_coarse_p1_constraint);
  }

  FEProblem::init();
}
