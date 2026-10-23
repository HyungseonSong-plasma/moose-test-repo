#include "PhysicsBoundaryLayerRefineGenerator.h"

#include "MooseMeshUtils.h"

#include "libmesh/elem.h"
#include "libmesh/mesh_refinement.h"

#include <set>
#include <tuple>
#include <vector>

registerMooseObject("PhysicsApp", PhysicsBoundaryLayerRefineGenerator);

InputParameters
PhysicsBoundaryLayerRefineGenerator::validParams()
{
  InputParameters params = MeshGenerator::validParams();
  params.addClassDescription(
      "Refines exactly one level of the first N face-neighbor element layers measured inward from "
      "one or more exterior sidesets.");
  params.addRequiredParam<MeshGeneratorName>("input", "Input mesh to refine.");
  params.addRequiredParam<std::vector<BoundaryName>>(
      "boundaries", "Exterior boundaries from which inward element-layer distance is measured.");
  params.addRangeCheckedParam<unsigned int>(
      "layers", 1, "layers > 0", "Number of cumulative face-neighbor layers to refine.");
  params.addParam<bool>(
      "enable_neighbor_refinement",
      true,
      "Allow libMesh conformity refinement. The selected layer set itself is always refined once.");
  return params;
}

PhysicsBoundaryLayerRefineGenerator::PhysicsBoundaryLayerRefineGenerator(
    const InputParameters & parameters)
  : MeshGenerator(parameters),
    _input(getMesh("input")),
    _boundaries(getParam<std::vector<BoundaryName>>("boundaries")),
    _layers(getParam<unsigned int>("layers")),
    _enable_neighbor_refinement(getParam<bool>("enable_neighbor_refinement"))
{
}

std::unique_ptr<MeshBase>
PhysicsBoundaryLayerRefineGenerator::generate()
{
  const auto boundary_ids = MooseMeshUtils::getBoundaryIDs(*_input, _boundaries, false);
  for (std::size_t i = 0; i < boundary_ids.size(); ++i)
    if (boundary_ids[i] == Moose::INVALID_BOUNDARY_ID)
      paramError("boundaries", "Boundary '", _boundaries[i], "' was not found in the mesh.");

  std::unique_ptr<MeshBase> mesh = std::move(_input);
  if (!mesh->is_prepared())
    mesh->prepare_for_use();

  // This bounded discriminator is intentionally serial/replicated. A distributed
  // implementation would need explicit frontier communication between ranks.
  if (!mesh->is_serial())
    mooseError("PhysicsBoundaryLayerRefineGenerator currently requires a serial/replicated mesh.");

  const std::set<boundary_id_type> requested_boundaries(boundary_ids.begin(), boundary_ids.end());
  const auto side_list = mesh->get_boundary_info().build_active_side_list();

  std::set<dof_id_type> selected;
  std::set<dof_id_type> frontier;

  for (const auto & entry : side_list)
    if (requested_boundaries.count(std::get<2>(entry)))
    {
      const auto elem_id = std::get<0>(entry);
      selected.insert(elem_id);
      frontier.insert(elem_id);
    }

  if (selected.empty())
    paramError("boundaries", "No active elements touch the requested boundaries.");

  // L1 is the sideset-touching element set. Each additional layer is one
  // face-neighbor hop farther into the same subdomain.
  for (unsigned int layer = 1; layer < _layers; ++layer)
  {
    std::set<dof_id_type> next_frontier;
    for (const auto elem_id : frontier)
    {
      const Elem * elem = mesh->elem_ptr(elem_id);
      for (unsigned int side = 0; side < elem->n_sides(); ++side)
      {
        const Elem * neighbor = elem->neighbor_ptr(side);
        if (!neighbor || !neighbor->active())
          continue;
        if (neighbor->subdomain_id() != elem->subdomain_id())
          continue;
        if (selected.insert(neighbor->id()).second)
          next_frontier.insert(neighbor->id());
      }
    }
    frontier = std::move(next_frontier);
    if (frontier.empty())
      break;
  }

  for (const auto elem_id : selected)
    mesh->elem_ptr(elem_id)->set_refinement_flag(Elem::REFINE);

  mooseInfo("PhysicsBoundaryLayerRefineGenerator: layers=",
            _layers,
            ", selected coarse elements=",
            selected.size());

  libMesh::MeshRefinement refinement(*mesh);
  if (!_enable_neighbor_refinement)
    refinement.face_level_mismatch_limit() = 0;
  refinement.refine_elements();

  return mesh;
}
