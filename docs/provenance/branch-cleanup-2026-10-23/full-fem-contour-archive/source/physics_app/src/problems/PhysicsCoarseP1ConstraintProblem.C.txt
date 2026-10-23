#include "PhysicsCoarseP1ConstraintProblem.h"

#include "NonlinearSystemBase.h"

#include "libmesh/boundary_info.h"
#include "libmesh/dof_map.h"
#include "libmesh/elem.h"
#include "libmesh/mesh_base.h"
#include "libmesh/node.h"
#include "libmesh/point.h"

#include <set>
#include <utility>

registerMooseObject("PhysicsApp", PhysicsCoarseP1ConstraintProblem);

namespace
{
class CoarseP1MidpointConstraint : public libMesh::System::Constraint
{
public:
  CoarseP1MidpointConstraint(libMesh::System & system,
                             std::string variable,
                             bool auto_detect_refinement_midpoints,
                             std::vector<dof_id_type> secondary_nodes,
                             std::vector<dof_id_type> primary_nodes_a,
                             std::vector<dof_id_type> primary_nodes_b)
    : _system(system),
      _variable(std::move(variable)),
      _auto_detect_refinement_midpoints(auto_detect_refinement_midpoints),
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

    const auto add_constraint = [&](const Node & secondary, const Node & primary_a, const Node & primary_b) {
      const auto secondary_dof =
          secondary.dof_number(_system.number(), variable_number, /*component=*/0);

      // Native libMesh hanging-node constraints are created before user constraints.
      // They already preserve coarse-P1 interpolation at the refined/unrefined interface.
      if (dof_map.is_constrained_dof(secondary_dof))
        return;

      const auto primary_a_dof =
          primary_a.dof_number(_system.number(), variable_number, /*component=*/0);
      const auto primary_b_dof =
          primary_b.dof_number(_system.number(), variable_number, /*component=*/0);

      libMesh::DofConstraintRow row;
      row[primary_a_dof] = 0.5;
      row[primary_b_dof] = 0.5;
      dof_map.add_constraint_row(secondary_dof, row, /*forbid_constraint_overwrite=*/true);
    };

    if (_auto_detect_refinement_midpoints)
    {
      // The discriminator uses one h-refinement level on a subset of a linear TRI3 mesh.
      // Preserve the original P1 potential space by constraining every unconstrained
      // interior edge midpoint to the two level-0 edge endpoints. Boundary midpoints
      // are left to the physical Dirichlet BC, while hanging midpoints are already
      // owned by libMesh's native AMR constraints.
      for (auto elem_it = mesh.elements_begin(); elem_it != mesh.elements_end(); ++elem_it)
      {
        const Elem * parent = *elem_it;
        if (!parent || parent->level() != 0 || !parent->has_children())
          continue;

        for (unsigned int side = 0; side < parent->n_sides(); ++side)
        {
          std::vector<boundary_id_type> side_boundary_ids;
          mesh.get_boundary_info().boundary_ids(parent, side, side_boundary_ids);
          if (!side_boundary_ids.empty())
            continue;

          const auto local_side_nodes = parent->nodes_on_side(side);
          if (local_side_nodes.size() != 2)
            libmesh_error_msg(
                "Automatic coarse-P1 midpoint detection requires linear two-node element sides.");

          const Node & primary_a = parent->node_ref(local_side_nodes[0]);
          const Node & primary_b = parent->node_ref(local_side_nodes[1]);
          const Point midpoint = (primary_a + primary_b) * 0.5;

          const Node * secondary = nullptr;
          for (unsigned int child_index = 0; child_index < parent->n_children() && !secondary;
               ++child_index)
          {
            const Elem * child = parent->child_ptr(child_index);
            if (!child)
              continue;
            for (unsigned int node_index = 0; node_index < child->n_nodes(); ++node_index)
            {
              const Node * candidate = child->node_ptr(node_index);
              if (candidate->id() != primary_a.id() && candidate->id() != primary_b.id() &&
                  candidate->absolute_fuzzy_equals(midpoint))
              {
                secondary = candidate;
                break;
              }
            }
          }

          if (!secondary)
            libmesh_error_msg("Could not locate a refinement midpoint on a refined level-0 side.");

          add_constraint(*secondary, primary_a, primary_b);
        }
      }
      return;
    }

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

      add_constraint(*secondary, *primary_a, *primary_b);
    }
  }

private:
  libMesh::System & _system;
  const std::string _variable;
  const bool _auto_detect_refinement_midpoints;
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
  params.addParam<bool>("coarse_p1_auto_detect_refinement_midpoints",
                        false,
                        "Automatically find one-level refinement midpoint DOFs from the libMesh "
                        "refinement tree and constrain unconstrained interior midpoints.");
  params.addParam<std::vector<dof_id_type>>(
      "coarse_p1_secondary_nodes", {}, "Explicit refinement midpoint node ids to constrain.");
  params.addParam<std::vector<dof_id_type>>(
      "coarse_p1_primary_nodes_a", {}, "First coarse-edge endpoint for each explicit midpoint.");
  params.addParam<std::vector<dof_id_type>>(
      "coarse_p1_primary_nodes_b", {}, "Second coarse-edge endpoint for each explicit midpoint.");
  params.addClassDescription(
      "FEProblem that attaches exact libMesh DofMap midpoint constraints before system init so a "
      "refined transport mesh can retain the original coarse P1 potential space.");
  return params;
}

PhysicsCoarseP1ConstraintProblem::PhysicsCoarseP1ConstraintProblem(
    const InputParameters & parameters)
  : FEProblem(parameters),
    _constrained_variable(getParam<std::string>("coarse_p1_variable")),
    _auto_detect_refinement_midpoints(
        getParam<bool>("coarse_p1_auto_detect_refinement_midpoints")),
    _secondary_nodes(getParam<std::vector<dof_id_type>>("coarse_p1_secondary_nodes")),
    _primary_nodes_a(getParam<std::vector<dof_id_type>>("coarse_p1_primary_nodes_a")),
    _primary_nodes_b(getParam<std::vector<dof_id_type>>("coarse_p1_primary_nodes_b"))
{
  if (_auto_detect_refinement_midpoints &&
      (!_secondary_nodes.empty() || !_primary_nodes_a.empty() || !_primary_nodes_b.empty()))
    paramError("coarse_p1_auto_detect_refinement_midpoints",
               "Automatic and explicit coarse-P1 midpoint specifications may not be mixed.");

  if (!_auto_detect_refinement_midpoints && _secondary_nodes.empty())
    paramError("coarse_p1_secondary_nodes",
               "At least one explicit midpoint is required unless automatic detection is enabled.");

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
    _coarse_p1_constraint = std::make_unique<CoarseP1MidpointConstraint>(
        system,
        _constrained_variable,
        _auto_detect_refinement_midpoints,
        _secondary_nodes,
        _primary_nodes_a,
        _primary_nodes_b);
    system.attach_constraint_object(*_coarse_p1_constraint);
  }

  FEProblem::init();
}
