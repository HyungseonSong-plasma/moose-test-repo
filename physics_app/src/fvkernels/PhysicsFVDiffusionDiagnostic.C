#include "PhysicsFVDiffusionDiagnostic.h"

#include "metaphysicl/raw_type.h"

#include <algorithm>
#include <iomanip>
#include <iostream>
#include <sstream>

registerMooseObject("PhysicsApp", PhysicsFVDiffusionDiagnostic);

InputParameters
PhysicsFVDiffusionDiagnostic::validParams()
{
  auto params = FVDiffusion::validParams();
  params.addClassDescription(
      "Diagnostic-only FVDiffusion wrapper that reports the framework grad(u).n used by the "
      "parent diffusion residual on selected internal faces and, optionally, selected side-set "
      "faces. The diagnostic does not change the parent residual.");
  params.addRequiredParam<std::vector<unsigned int>>(
      "diagnostic_element_ids",
      "Governed Exodus element IDs (elem_num_map values, one-based) defining plasma cells whose "
      "internal or side-set faces may be reported. libMesh Elem::id() is converted to this "
      "one-based convention at the diagnostic boundary.");
  params.addParam<bool>(
      "diagnostic_boundary_faces",
      false,
      "If true, report side-set faces touching a selected diagnostic element. Physical boundary "
      "membership is detected from FaceInfo boundary IDs, not neighborPtr() or isInternalFace(), "
      "because plasma-solid interfaces can be mesh-internal faces and Dirichlet reconstruction "
      "can use ghost neighbors.");
  return params;
}

PhysicsFVDiffusionDiagnostic::PhysicsFVDiffusionDiagnostic(const InputParameters & params)
  : FVDiffusion(params),
    _diagnostic_element_ids(getParam<std::vector<unsigned int>>("diagnostic_element_ids")),
    _diagnostic_boundary_faces(getParam<bool>("diagnostic_boundary_faces"))
{
}

bool
PhysicsFVDiffusionDiagnostic::probeFace() const
{
  if (!_face_info)
    return false;

  // Exodus elem_num_map is one-based relative to libMesh Elem::id() for this governed mesh.
  // Keep all external evidence in the governed Exodus convention and convert only here.
  const auto selected = [this](const dof_id_type libmesh_id)
  {
    const auto exodus_id = static_cast<unsigned int>(libmesh_id + 1);
    return std::find(_diagnostic_element_ids.begin(), _diagnostic_element_ids.end(), exodus_id) !=
           _diagnostic_element_ids.end();
  };

  const bool elem_selected = selected(_face_info->elem().id());
  const bool neighbor_selected = _face_info->neighborPtr() && selected(_face_info->neighbor().id());
  const bool has_boundary_tag = !_face_info->boundaryIDs().empty();

  // A physical plasma-wall side set can be a mesh-internal plasma/solid interface, while a
  // Dirichlet exterior face can carry a ghost neighbor. Therefore topological neighbor existence
  // and variable-domain internal-face semantics are not physical-boundary classifiers.
  if (_diagnostic_boundary_faces && has_boundary_tag && (elem_selected || neighbor_selected))
    return true;

  // Internal diagnostic faces remain available as a supporting cross-check only.
  return !has_boundary_tag && elem_selected && neighbor_selected;
}

ADReal
PhysicsFVDiffusionDiagnostic::computeQpResidual()
{
  // Residual equivalence is the primary invariant: evaluate and return the exact parent result.
  const ADReal parent_residual = FVDiffusion::computeQpResidual();
  if (!probeFace())
    return parent_residual;

  const auto state = determineState();
  const ADReal dudn_parent = gradUDotNormal(state, _correct_skewness);

  const auto selected = [this](const dof_id_type libmesh_id)
  {
    const auto exodus_id = static_cast<unsigned int>(libmesh_id + 1);
    return std::find(_diagnostic_element_ids.begin(), _diagnostic_element_ids.end(), exodus_id) !=
           _diagnostic_element_ids.end();
  };
  const bool elem_selected = selected(_face_info->elem().id());
  const bool neighbor_selected = _face_info->neighborPtr() && selected(_face_info->neighbor().id());
  const bool has_boundary_tag = !_face_info->boundaryIDs().empty();

  // For a tagged physical face, standardize every reported directional quantity relative to the
  // selected plasma cell: normal points from that plasma cell across the face (plasma-outward).
  // FVFluxKernel::_normal is elem->neighbor, so flip it if the selected plasma cell is neighbor.
  Real orientation = 1.0;
  dof_id_type selected_libmesh_id = _face_info->elem().id();
  ADReal selected_value = _var(elemArg(), state);
  if (has_boundary_tag && !elem_selected && neighbor_selected)
  {
    orientation = -1.0;
    selected_libmesh_id = _face_info->neighbor().id();
    selected_value = _var(neighborArg(), state);
  }
  const auto selected_exodus_id = static_cast<unsigned int>(selected_libmesh_id + 1);

  const ADReal dudn_selected_outward = orientation * dudn_parent;
  const RealVectorValue selected_outward_normal = orientation * _normal;

  Real central_dudn = 0.0;
  Real u_neighbor = 0.0;
  if (!has_boundary_tag && _face_info->neighborPtr())
  {
    const ADReal elem_value = _var(elemArg(), state);
    const ADReal neighbor_value = _var(neighborArg(), state);
    u_neighbor = MetaPhysicL::raw_value(neighbor_value);
    central_dudn =
        (u_neighbor - MetaPhysicL::raw_value(elem_value)) /
        _face_info->dCNMag() * (_face_info->eCN() * _normal);
  }

  std::ostringstream boundary_ids;
  bool first = true;
  for (const auto id : _face_info->boundaryIDs())
  {
    if (!first)
      boundary_ids << ',';
    boundary_ids << id;
    first = false;
  }

  const auto & fc = _face_info->faceCentroid();
  std::cout << std::setprecision(17)
            << "ISSUE228_DIFF"
            << " face_type=" << (has_boundary_tag ? "boundary" : "internal")
            << " elem=" << selected_exodus_id;
  if (!has_boundary_tag && _face_info->neighborPtr())
    std::cout << " neighbor=" << static_cast<unsigned int>(_face_info->neighbor().id() + 1);
  std::cout << " boundary_ids=" << boundary_ids.str()
            << " face_x=" << fc(0)
            << " face_y=" << fc(1)
            << " normal_x=" << selected_outward_normal(0)
            << " normal_y=" << selected_outward_normal(1)
            << " dcn_mag=" << _face_info->dCNMag()
            << " ecn_dot_normal=" << orientation * (_face_info->eCN() * _normal)
            << " u_elem=" << MetaPhysicL::raw_value(selected_value);
  if (!has_boundary_tag && _face_info->neighborPtr())
    std::cout << " u_neighbor=" << u_neighbor
              << " central_dudn=" << central_dudn
              << " nonorth_corr_dudn=" << MetaPhysicL::raw_value(dudn_parent) - central_dudn;
  std::cout << " actual_dudn=" << MetaPhysicL::raw_value(dudn_selected_outward)
            << " residual=" << MetaPhysicL::raw_value(parent_residual)
            << std::endl;

  return parent_residual;
}
